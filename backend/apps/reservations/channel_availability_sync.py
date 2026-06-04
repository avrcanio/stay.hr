from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import transaction

from apps.reservations.models import Reservation, ReservationUnit

_suppress_unit_sync: ContextVar[int] = ContextVar("suppress_unit_sync", default=0)


@contextmanager
def suppress_unit_availability_sync():
    token = _suppress_unit_sync.set(_suppress_unit_sync.get() + 1)
    try:
        yield
    finally:
        _suppress_unit_sync.reset(token)


def unit_availability_sync_suppressed() -> bool:
    return _suppress_unit_sync.get() > 0


def reservation_unit_codes(reservation: Reservation) -> frozenset[str]:
    codes = {
        row.unit.code
        for row in ReservationUnit.objects.filter(reservation=reservation).select_related("unit")
        if row.unit_id and row.unit.code
    }
    return frozenset(codes)


def queue_reservation_channel_availability_sync(reservation_id: int) -> None:
    """Enqueue Channex ARI push after unit assignment changes (PDF/XLS/manual)."""
    from apps.integrations.channel_manager.tasks import push_reservation_availability_task

    transaction.on_commit(
        lambda rid=reservation_id: push_reservation_availability_task.delay(rid)
    )


def queue_sync_if_units_changed(
    reservation: Reservation,
    *,
    before_codes: frozenset[str],
) -> bool:
    after_codes = reservation_unit_codes(reservation)
    if before_codes == after_codes:
        return False
    queue_reservation_channel_availability_sync(reservation.pk)
    return True
