from __future__ import annotations

from apps.integrations.models import SalesChannel

DEFAULT_SALES_CHANNEL = SalesChannel.BOOKING_COM


def parse_sales_channel(raw: str | None) -> str:
    value = (raw or DEFAULT_SALES_CHANNEL).strip().lower()
    valid = {choice.value for choice in SalesChannel}
    if value not in valid:
        raise ValueError(f"Invalid sales_channel: {raw!r}")
    return value
