"""Property self-service key pickup schedule helpers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from apps.properties.models import Property, SelfServiceMode


def normalize_self_service_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    config: dict[str, Any] = {}

    weekdays_raw = raw.get("weekdays")
    if isinstance(weekdays_raw, list):
        weekdays: list[int] = []
        for item in weekdays_raw:
            try:
                day = int(item)
            except (TypeError, ValueError):
                continue
            if 0 <= day <= 6 and day not in weekdays:
                weekdays.append(day)
        if weekdays:
            config["weekdays"] = weekdays

    dates_raw = raw.get("dates")
    if isinstance(dates_raw, list):
        dates: list[str] = []
        for item in dates_raw:
            text = str(item or "").strip()
            if not text:
                continue
            try:
                parsed = date.fromisoformat(text)
            except ValueError:
                continue
            iso = parsed.isoformat()
            if iso not in dates:
                dates.append(iso)
        if dates:
            config["dates"] = dates

    return config


def is_self_service_active(
    property: Property,
    on_date: date,
    *,
    now: datetime | None = None,
) -> bool:
    """
    Return whether the key-guide self-service card should be shown for ``on_date``.

    ``now`` is accepted for call-site symmetry / future time-of-day rules; schedule and
    calendar modes currently key off the calendar date only.
    """
    del now  # reserved for future time-window rules
    mode = (property.self_service_mode or SelfServiceMode.OFF).strip()
    if mode == SelfServiceMode.OFF:
        return False
    if mode == SelfServiceMode.ALWAYS:
        return True

    config = normalize_self_service_config(property.self_service_config)
    if mode == SelfServiceMode.SCHEDULE:
        weekdays = config.get("weekdays") or []
        return on_date.weekday() in weekdays
    if mode == SelfServiceMode.CALENDAR:
        dates = config.get("dates") or []
        return on_date.isoformat() in dates
    return False
