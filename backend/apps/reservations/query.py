"""Reception timeline query helpers."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

PROPERTY_TIMEZONE = ZoneInfo("Europe/Zagreb")


def property_day_range(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    """
    Aware UTC datetimes for [from_date 00:00, to_date 00:00) in Europe/Zagreb.

    ``to_date`` is exclusive (same convention as period_to on the timeline API).
    """
    start_local = datetime.combine(from_date, time.min, tzinfo=PROPERTY_TIMEZONE)
    end_local = datetime.combine(to_date, time.min, tzinfo=PROPERTY_TIMEZONE)
    return start_local, end_local
