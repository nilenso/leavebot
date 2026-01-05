"""Date utilities for handling leave dates."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# Half-day time constants (in local timezone)
HALF_AM_START = time(11, 0)  # 11:00 AM
HALF_AM_END = time(15, 0)  # 3:00 PM
HALF_PM_START = time(15, 0)  # 3:00 PM
HALF_PM_END = time(19, 0)  # 7:00 PM


def get_half_day_times(
    leave_type: str,
    leave_date: date,
    timezone: str = "Asia/Kolkata",
) -> tuple[datetime, datetime]:
    """Get start/end times for half_am (11:00-15:00) or half_pm (15:00-19:00)."""
    tz = ZoneInfo(timezone)

    if leave_type == "half_am":
        start_time = HALF_AM_START
        end_time = HALF_AM_END
    else:  # half_pm
        start_time = HALF_PM_START
        end_time = HALF_PM_END

    start_dt = datetime.combine(leave_date, start_time, tzinfo=tz)
    end_dt = datetime.combine(leave_date, end_time, tzinfo=tz)

    return start_dt, end_dt
