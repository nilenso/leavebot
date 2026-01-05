"""Slack Block Kit message builders."""

from datetime import date

from leave_bot.bot.parser import ParsedLeave
from leave_bot.models.leave import LeaveRecord


def build_confirmation_message(
    parsed: ParsedLeave,
    action_id: str,
    has_conflicts: bool = False,
    conflicting_dates: list[date] | None = None,
) -> list[dict]:
    blocks = []

    # Header
    if parsed.is_cancellation:
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🗑️ Leave Cancellation Request",
                    "emoji": True,
                },
            }
        )
    else:
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📅 Leave Request",
                    "emoji": True,
                },
            }
        )

    # Summary section
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary:* {parsed.original_text_summary}",
            },
        }
    )

    # Dates section
    if parsed.dates:
        date_lines = []
        for leave_date in parsed.dates:
            type_emoji = {
                "full": "📆",
                "half_am": "🌅",
                "half_pm": "🌆",
            }.get(leave_date.type, "📆")

            type_label = {
                "full": "Full Day",
                "half_am": "Morning Half",
                "half_pm": "Afternoon Half",
            }.get(leave_date.type, leave_date.type)

            category_label = "🤒 Sick" if leave_date.category == "sick" else "🏖️ Vacation"

            # Check if this date conflicts
            is_conflict = False
            if conflicting_dates:
                try:
                    d = date.fromisoformat(leave_date.date)
                    is_conflict = d in conflicting_dates
                except ValueError:
                    pass

            conflict_marker = " ⚠️ *CONFLICT*" if is_conflict else ""
            date_lines.append(
                f"{type_emoji} {leave_date.date} - {type_label} ({category_label}){conflict_marker}"
            )

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Dates:*\n" + "\n".join(date_lines),
                },
            }
        )

    # Confidence indicator
    confidence_emoji = {
        "high": "✅",
        "medium": "⚠️",
        "low": "❓",
    }.get(parsed.confidence, "❓")

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{confidence_emoji} Confidence: {parsed.confidence.upper()}",
                },
            ],
        }
    )

    # Ambiguity notes if present
    if parsed.ambiguity_notes:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"ℹ️ {parsed.ambiguity_notes}",
                    },
                ],
            }
        )

    # Conflict warning
    if has_conflicts and conflicting_dates:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ *Warning:* Some dates conflict with existing leave records. Confirming will override them.",
                },
            }
        )

    # Divider before buttons
    blocks.append({"type": "divider"})

    # Action buttons
    buttons = [
        {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "✅ Confirm",
                "emoji": True,
            },
            "style": "primary",
            "action_id": f"leave_confirm_{action_id}",
            "value": action_id,
        },
        {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "❌ Cancel",
                "emoji": True,
            },
            "style": "danger",
            "action_id": f"leave_cancel_{action_id}",
            "value": action_id,
        },
    ]

    blocks.append(
        {
            "type": "actions",
            "elements": buttons,
        }
    )

    return blocks


def build_success_message(
    leave_records: list[LeaveRecord],
    is_cancellation: bool = False,
) -> list[dict]:
    blocks = []

    if is_cancellation:
        header_text = "✅ Leave Cancelled"
        status_text = "Your leave has been cancelled and removed from Calendar and Harvest."
    else:
        header_text = "✅ Leave Confirmed"
        status_text = "Your leave has been synced to Calendar and Harvest."

    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
                "emoji": True,
            },
        }
    )

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": status_text,
            },
        }
    )

    # List dates
    if leave_records:
        date_list = []
        for record in leave_records:
            type_label = {
                "full": "Full Day",
                "half_am": "Morning",
                "half_pm": "Afternoon",
            }.get(record.leave_type.value, record.leave_type.value)
            date_list.append(f"• {record.date.isoformat()} ({type_label})")

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Dates:*\n" + "\n".join(date_list),
                },
            }
        )

    return blocks


def build_error_message(error: str, retry_available: bool = False) -> list[dict]:
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "❌ Error",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Sorry, something went wrong:\n```{error}```",
            },
        },
    ]

    if retry_available:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "The system will automatically retry. If the problem persists, please contact an admin.",
                    },
                ],
            }
        )

    return blocks


def build_clarification_request() -> list[dict]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": '🤔 I couldn\'t determine the specific dates for your leave request. Could you please clarify?\n\nFor example:\n• "Tomorrow"\n• "5th to 7th January"\n• "Next Monday and Tuesday"',
            },
        },
    ]


def build_not_registered_message() -> list[dict]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "👋 Hi! It looks like you're not registered in the leave system yet.\n\nPlease contact your admin to get set up, then try again.",
            },
        },
    ]


def build_expired_message() -> list[dict]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⏰ This leave request has expired. Please post a new message to request leave.",
            },
        },
    ]
