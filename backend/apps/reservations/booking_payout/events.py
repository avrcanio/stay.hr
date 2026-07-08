"""In-process events for booking payout line sync."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from apps.reservations.booking_payout.types import FieldDiff, SyncPolicy


@dataclass(frozen=True)
class BookingPayoutLineSynced:
    line_id: int
    reservation_id: int
    import_id: int
    policy: SyncPolicy
    result: str
    applied_by_id: int | None
    field_diffs: tuple[FieldDiff, ...]


_listeners: list[Callable[[BookingPayoutLineSynced], None]] = []


def subscribe_booking_payout_line_synced(
    handler: Callable[[BookingPayoutLineSynced], None],
) -> None:
    _listeners.append(handler)


def emit_booking_payout_line_synced(event: BookingPayoutLineSynced) -> None:
    for handler in list(_listeners):
        handler(event)
