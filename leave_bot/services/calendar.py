"""Google Calendar service for creating and managing leave events."""

from datetime import date, timedelta
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from leave_bot.config import get_settings
from leave_bot.models.leave import LeaveType
from leave_bot.utils.dates import get_half_day_times
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def group_consecutive_dates(dates: list[date]) -> list[list[date]]:
    """Group consecutive dates into spans.

    Example:
        [Jan 5, Jan 6, Jan 7, Jan 10, Jan 11] -> [[Jan 5, Jan 6, Jan 7], [Jan 10, Jan 11]]

    Args:
        dates: List of dates to group (will be sorted)

    Returns:
        List of date groups, where each group is a list of consecutive dates
    """
    if not dates:
        return []

    sorted_dates = sorted(dates)
    groups: list[list[date]] = []
    current_group: list[date] = [sorted_dates[0]]

    for i in range(1, len(sorted_dates)):
        current_date = sorted_dates[i]
        prev_date = sorted_dates[i - 1]

        if current_date - prev_date == timedelta(days=1):
            # Consecutive, add to current group
            current_group.append(current_date)
        else:
            # Not consecutive, start a new group
            groups.append(current_group)
            current_group = [current_date]

    # Don't forget the last group
    groups.append(current_group)

    return groups


class CalendarService:
    """Google Calendar client for leave event management."""

    def __init__(self) -> None:
        settings = get_settings()

        credentials = service_account.Credentials.from_service_account_info(
            settings.google_service_account_info,
            scopes=SCOPES,
        )

        self.calendar_id = settings.google_calendar_id
        self.service: Any = build("calendar", "v3", credentials=credentials)
        logger.info("calendar_service_initialized", calendar_id=self.calendar_id)

    async def create_event(
        self,
        user_name: str,
        user_email: str | None,
        leave_date: date,
        leave_type: LeaveType,
        timezone: str = "Asia/Kolkata",
    ) -> str:
        if leave_type == LeaveType.full:
            summary = f"Leave - {user_name}"
        elif leave_type == LeaveType.half_am:
            summary = f"Leave (Morning) - {user_name}"
        else:
            summary = f"Leave (Afternoon) - {user_name}"

        event_body: dict[str, Any] = {
            "summary": summary,
            "eventType": "default",
        }

        # Set timing based on leave type
        if leave_type == LeaveType.full:
            # All-day event
            event_body["start"] = {"date": leave_date.isoformat()}
            event_body["end"] = {"date": leave_date.isoformat()}
        else:
            # Half-day timed event
            start_dt, end_dt = get_half_day_times(leave_type.value, leave_date, timezone)
            event_body["start"] = {
                "dateTime": start_dt.isoformat(),
                "timeZone": timezone,
            }
            event_body["end"] = {
                "dateTime": end_dt.isoformat(),
                "timeZone": timezone,
            }

        # Note: Not adding attendees - requires Domain-Wide Delegation for service accounts
        # The event summary already includes the user's name

        logger.info(
            "creating_calendar_event",
            user_name=user_name,
            leave_date=leave_date.isoformat(),
            leave_type=leave_type.value,
        )

        # Create the event
        event = self.service.events().insert(calendarId=self.calendar_id, body=event_body).execute()

        event_id = event["id"]
        logger.info("calendar_event_created", event_id=event_id)
        return event_id

    async def create_spanning_event(
        self,
        user_name: str,
        user_email: str | None,
        start_date: date,
        end_date: date,
    ) -> str:
        """Create a multi-day spanning calendar event.

        Args:
            user_name: Display name for the event summary
            user_email: User's email (currently unused, for future attendee support)
            start_date: First day of leave (inclusive)
            end_date: Last day of leave (inclusive)

        Returns:
            The created event ID
        """
        summary = f"Leave - {user_name}"

        # Google Calendar uses exclusive end dates, so add 1 day
        exclusive_end = end_date + timedelta(days=1)

        event_body: dict[str, Any] = {
            "summary": summary,
            "eventType": "default",
            "start": {"date": start_date.isoformat()},
            "end": {"date": exclusive_end.isoformat()},
        }

        logger.info(
            "creating_spanning_calendar_event",
            user_name=user_name,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            span_days=(end_date - start_date).days + 1,
        )

        event = self.service.events().insert(calendarId=self.calendar_id, body=event_body).execute()

        event_id = event["id"]
        logger.info("calendar_spanning_event_created", event_id=event_id)
        return event_id

    async def delete_event(self, event_id: str) -> bool:
        logger.info("deleting_calendar_event", event_id=event_id)

        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()
            logger.info("calendar_event_deleted", event_id=event_id)
            return True
        except HttpError as e:
            logger.error("calendar_event_delete_failed", event_id=event_id, error=str(e))
            raise

    async def check_connection(self) -> bool:
        try:
            self.service.calendarList().list(maxResults=1).execute()
            return True
        except HttpError as e:
            logger.error("calendar_health_check_failed", error=str(e))
            return False
