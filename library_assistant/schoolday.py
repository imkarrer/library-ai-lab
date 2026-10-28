"""The end of the school day, in the Install's own time zone.

The Purge runs at it (ADR-0003) and Registration refuses an expiry past it (ADR-0010).
Times go in and come out timezone-aware, as UTC; the local date is the school's, so a
daylight-saving change moves the UTC instant, not the wall-clock end.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from library_assistant.config import Settings


def _end_on(local_date: date, settings: Settings) -> datetime:
    end = time.fromisoformat(settings.school_day_end)
    zone = ZoneInfo(settings.school_timezone)
    return datetime.combine(local_date, end, tzinfo=zone).astimezone(UTC)


def _local_date(moment: datetime, settings: Settings) -> date:
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    return moment.astimezone(ZoneInfo(settings.school_timezone)).date()


def school_date(moment: datetime, settings: Settings) -> date:
    """The school's local date at `moment`: the day a record belongs to."""
    return _local_date(moment, settings)


def school_day_end_for(moment: datetime, settings: Settings) -> datetime:
    """The end of the school day on `moment`'s local date."""
    return _end_on(_local_date(moment, settings), settings)


def last_day_end_before(moment: datetime, settings: Settings) -> datetime:
    """The most recent end of a school day at or before `moment`."""
    local_date = _local_date(moment, settings)
    end = _end_on(local_date, settings)
    if end <= moment:
        return end
    return _end_on(local_date - timedelta(days=1), settings)
