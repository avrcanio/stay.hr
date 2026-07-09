"""Reception-facing guest web check-in progress DTO."""

from __future__ import annotations

from apps.reservations.checkin_readiness import (
    effective_session_status,
    slot_validation_results,
)
from apps.reservations.guest_checkin_session import (
    build_guest_checkin_url,
    get_active_session,
)
from apps.reservations.guest_validation import SlotReadinessStatus
from apps.reservations.models import GuestCheckInSessionStatus, Reservation


def checkin_progress_for_reservation(reservation: Reservation) -> dict:
    """Build check-in progress snapshot for reception timeline/detail APIs."""
    validations = slot_validation_results(reservation)
    required_slots = len(validations)
    if required_slots == 0:
        return _empty_progress()

    ready_count = sum(1 for slot in validations if slot.status == SlotReadinessStatus.READY)
    waiting_positions = [
        slot.position for slot in validations if slot.status != SlotReadinessStatus.READY
    ]

    session = get_active_session(reservation)
    if session is None:
        return {
            "required_slots": required_slots,
            "ready_slots": ready_count,
            "waiting_positions": waiting_positions,
            "session_status": None,
            "effective_status": None,
            "last_activity_at": None,
            "checkin_url": None,
        }

    effective = effective_session_status(session, reservation)
    checkin_url = (
        build_guest_checkin_url(session, reservation)
        if session.status == GuestCheckInSessionStatus.ACTIVE
        else None
    )
    last_activity_at = session.last_activity_at
    return {
        "required_slots": required_slots,
        "ready_slots": ready_count,
        "waiting_positions": waiting_positions,
        "session_status": session.status,
        "effective_status": effective,
        "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
        "checkin_url": checkin_url,
    }


def _empty_progress() -> dict:
    return {
        "required_slots": 0,
        "ready_slots": 0,
        "waiting_positions": [],
        "session_status": None,
        "effective_status": None,
        "last_activity_at": None,
        "checkin_url": None,
    }
