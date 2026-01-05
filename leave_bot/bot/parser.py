"""LLM-based leave message parser using OpenAI."""

import json
from datetime import date, datetime
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from openai import OpenAI
from openai.types.responses import (
    ResponseFormatTextJSONSchemaConfigParam,
    ResponseInputParam,
    ResponseTextConfigParam,
)
from pydantic import BaseModel, Field

from leave_bot.config import get_settings
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)


class ThreadMessage(BaseModel):
    """A message from a thread for context."""

    text: str = Field(..., description="Message text content")
    user_id: str = Field(..., description="Slack user ID of the sender")
    ts: str = Field(..., description="Message timestamp")


class LeaveDate(BaseModel):
    """A single leave date with type and category."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    type: Literal["full", "half_am", "half_pm"] = Field(..., description="Type of leave")
    category: Literal["vacation", "sick"] = Field(..., description="Category of leave")


class ParsedLeave(BaseModel):
    """Result of parsing a leave message."""

    is_leave_request: bool = Field(..., description="Whether this is a leave request")
    is_cancellation: bool = Field(..., description="Whether this is cancelling existing leave")
    confidence: Literal["high", "medium", "low"] = Field(
        ..., description="Confidence level of parsing"
    )
    dates: list[LeaveDate] = Field(..., description="List of leave dates")
    original_text_summary: str = Field(..., description="Brief summary of the original message")
    ambiguity_notes: str = Field(..., description="Notes about any ambiguities, or empty string")


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

8. Thread Context:
   - When conversation history is provided, use it to understand follow-up messages
   - Follow-ups like "yes", "confirmed", "sounds good" after a leave parsing clarification should be treated as confirmations
   - If the user says "make it a half day instead", look at the previous context to understand what dates they're referring to
   - Modifications like "actually, just the 5th" refer to dates mentioned in thread context
   - Treat "yes, confirmed" or similar affirmations as NOT leave requests (they're button confirmations, not new leave)

EXAMPLES:
- "On leave tomorrow" → high confidence, 1 full day vacation
- "Taking sick leave 5th-7th" → high confidence, 3 sick days
- "Half day tomorrow afternoon" → high confidence, 1 half_pm vacation
- "WFH today" → NOT a leave request
- "Cancel my leave for tomorrow" → cancellation request

THREAD CONTEXT EXAMPLES:
- Thread: ["Taking leave on the 10th"] + Current: "make it a half day instead" → 1 half_am vacation on the 10th
- Thread: ["I need leave 5th-7th"] + Current: "actually just the 5th and 6th" → 2 full day vacation dates
- Thread: ["Leave tomorrow?"] + Current: "yes, confirmed" → NOT a leave request (this is an affirmation, not a new request)
"""


async def parse_leave_message(
    message_text: str,
    user_timezone: str = "Asia/Kolkata",
    reference_date: date | None = None,
    thread_context: list[ThreadMessage] | None = None,
) -> ParsedLeave:
    """Parse a leave message using OpenAI structured output.

    Args:
        message_text: The current message to parse.
        user_timezone: User's timezone for date calculations.
        reference_date: Reference date for relative date parsing.
        thread_context: Optional list of previous messages in the thread for context.
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    if reference_date is None:
        tz = ZoneInfo(user_timezone)
        reference_date = datetime.now(tz).date()

    # Build conversation history section if thread context exists
    conversation_history = ""
    if thread_context:
        history_lines = []
        for msg in thread_context:
            history_lines.append(f'- "{msg.text}"')
        conversation_history = f"""
Conversation History (previous messages in thread):
{chr(10).join(history_lines)}

"""

    # Build the user prompt with context
    user_prompt = f"""Parse this leave message:
{conversation_history}Current Message: "{message_text}"

Context:
- Current date: {reference_date.isoformat()} ({reference_date.strftime("%A")})
- User timezone: {user_timezone}
- Current year: {reference_date.year}

Extract structured leave information following the rules. If there is conversation history, use it to understand follow-up messages and modifications to previous requests."""

    logger.info(
        "parsing_leave_message",
        message_length=len(message_text),
        reference_date=reference_date.isoformat(),
        has_thread_context=thread_context is not None,
        thread_context_length=len(thread_context) if thread_context else 0,
    )

    try:
        input_messages = cast(
            ResponseInputParam,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        # Build schema with additionalProperties: false (required by OpenAI)
        schema = ParsedLeave.model_json_schema()
        schema["additionalProperties"] = False
        # Also fix nested $defs
        if "$defs" in schema:
            for def_schema in schema["$defs"].values():
                def_schema["additionalProperties"] = False

        json_schema_format: ResponseFormatTextJSONSchemaConfigParam = {
            "type": "json_schema",
            "name": "leave_parse_result",
            "schema": cast(dict[str, Any], schema),
            "strict": True,
        }
        text_config: ResponseTextConfigParam = {"format": json_schema_format}
        response = client.responses.create(
            model=settings.openai_model,
            input=input_messages,
            text=text_config,
            reasoning={"effort": "low"},
        )

        result = json.loads(response.output_text)
        parsed = ParsedLeave.model_validate(result)

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
            is_cancellation=False,
            confidence="low",
            dates=[],
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
