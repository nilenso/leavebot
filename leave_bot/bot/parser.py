"""LLM-based leave message parser using OpenAI."""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from pydantic import BaseModel, Field

from leave_bot.config import get_settings
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)


class LeaveDate(BaseModel):
    """A single leave date with type and category."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    type: Literal["full", "half_am", "half_pm"] = Field(default="full", description="Type of leave")
    category: Literal["vacation", "sick"] = Field(
        default="vacation", description="Category of leave"
    )


class ParsedLeave(BaseModel):
    """Result of parsing a leave message."""

    is_leave_request: bool = Field(..., description="Whether this is a leave request")
    is_cancellation: bool = Field(
        default=False, description="Whether this is cancelling existing leave"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium", description="Confidence level of parsing"
    )
    dates: list[LeaveDate] = Field(default_factory=list, description="List of leave dates")
    original_text_summary: str = Field(
        default="", description="Brief summary of the original message"
    )
    ambiguity_notes: str | None = Field(default=None, description="Notes about any ambiguities")


SYSTEM_PROMPT = """You are a leave message parser for a company Slack bot. Your job is to extract structured leave information from messages posted in the #wfh-leaves-ooo channel.

RULES:
1. Only parse actual leave requests. Ignore:
   - Work From Home (WFH) announcements (unless explicitly requesting leave)
   - Status updates that aren't leave requests
   - Questions about leave policy
   - Public holiday announcements

2. Date Parsing:
   - Parse relative dates (tomorrow, next Monday, the 5th) into absolute YYYY-MM-DD format
   - For date ranges like "5th to 10th", expand into individual dates
   - Skip weekends unless explicitly mentioned
   - If year is not specified, assume current year (or next year if date has passed)
   - Retroactive leave is allowed only for dates on or after January 1st of the current year

3. Leave Types:
   - "full" - Full day leave (default)
   - "half_am" - Morning half-day (first half)
   - "half_pm" - Afternoon half-day (second half)
   - Look for keywords: "half day", "first half", "second half", "morning", "afternoon"

4. Leave Categories:
   - "vacation" - Default for planned leave, PTO, personal time
   - "sick" - Sick leave, medical appointments, not feeling well

5. Cancellations:
   - Detect cancel/cancellation requests
   - Keywords: "cancel", "cancelling", "won't be taking", "changed plans"

6. Confidence Levels:
   - "high" - Clear, unambiguous leave request with specific dates
   - "medium" - Likely a leave request but some interpretation needed
   - "low" - Ambiguous message that needs clarification

7. Do NOT:
   - Parse messages that are just "WFH today" without leave context
   - Assume leave when someone mentions being busy or in meetings
   - Parse messages asking about leave balance or policy

EXAMPLES:
- "On leave tomorrow" → high confidence, 1 full day vacation
- "Taking sick leave 5th-7th" → high confidence, 3 sick days
- "Half day tomorrow afternoon" → high confidence, 1 half_pm vacation
- "WFH today" → NOT a leave request
- "Cancel my leave for tomorrow" → cancellation request
"""


async def parse_leave_message(
    message_text: str,
    user_timezone: str = "Asia/Kolkata",
    reference_date: date | None = None,
) -> ParsedLeave:
    """Parse a leave message using OpenAI structured output."""
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    if reference_date is None:
        tz = ZoneInfo(user_timezone)
        reference_date = datetime.now(tz).date()

    # Build the user prompt with context
    user_prompt = f"""Parse this leave message:

Message: "{message_text}"

Context:
- Current date: {reference_date.isoformat()} ({reference_date.strftime("%A")})
- User timezone: {user_timezone}
- Current year: {reference_date.year}

Extract structured leave information following the rules."""

    logger.info(
        "parsing_leave_message",
        message_length=len(message_text),
        reference_date=reference_date.isoformat(),
    )

    try:
        system_msg: ChatCompletionSystemMessageParam = {"role": "system", "content": SYSTEM_PROMPT}
        user_msg: ChatCompletionUserMessageParam = {"role": "user", "content": user_prompt}
        response = client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[system_msg, user_msg],
            response_format=ParsedLeave,
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            logger.warning("llm_returned_none", message=message_text[:100])
            return ParsedLeave(
                is_leave_request=False,
                confidence="low",
                original_text_summary="Failed to parse message",
            )

        logger.info(
            "message_parsed",
            is_leave_request=parsed.is_leave_request,
            is_cancellation=parsed.is_cancellation,
            confidence=parsed.confidence,
            num_dates=len(parsed.dates),
        )

        return parsed

    except Exception as e:
        logger.error("llm_parse_error", error=str(e))
        return ParsedLeave(
            is_leave_request=False,
            confidence="low",
            original_text_summary=f"Parse error: {e}",
            ambiguity_notes=str(e),
        )


def validate_parsed_dates(
    parsed: ParsedLeave,
    reference_date: date,
) -> tuple[list[LeaveDate], list[str]]:
    """Validate dates are not before Jan 1 of current year."""
    valid_dates: list[LeaveDate] = []
    warnings: list[str] = []

    earliest_allowed = date(reference_date.year, 1, 1)

    for leave_date in parsed.dates:
        try:
            parsed_date = date.fromisoformat(leave_date.date)

            # Check if date is before earliest allowed
            if parsed_date < earliest_allowed:
                warnings.append(f"{leave_date.date} is before Jan 1 {reference_date.year}")
                continue

            valid_dates.append(leave_date)

        except ValueError:
            warnings.append(f"Invalid date format: {leave_date.date}")

    return valid_dates, warnings
