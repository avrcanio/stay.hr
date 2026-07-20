"""WEB_GUEST document intake — slot-forced matching for web check-in OCR."""

from __future__ import annotations

from apps.reservations.document_expectations import expected_document_slots
from apps.reservations.document_intake_context import DocumentIntakeContext
from apps.reservations.document_intake_match import (
    _guest_display_name,
    _person_full_name,
    _reservation_label,
)
from apps.reservations.models import DocumentIntakeJobSource


def is_web_guest_slot_forced_job(ctx: DocumentIntakeContext) -> bool:
    job = ctx.job
    return (
        job.source == DocumentIntakeJobSource.WEB_GUEST
        and bool(job.guest_checkin_slot_position)
        and ctx.is_reservation_scoped
    )


def run_web_guest_matching_pipeline(
    *,
    ctx: DocumentIntakeContext,
    persons: list[dict],
) -> list[dict]:
    """Force each OCR person onto the guest at ``guest_checkin_slot_position``."""
    job = ctx.job
    reservation = ctx.reservation
    if reservation is None:
        return []

    position = int(job.guest_checkin_slot_position or 0)
    slots = expected_document_slots(reservation)
    if position < 1 or position > len(slots):
        return []

    target_guest = slots[position - 1]
    reservation_label = _reservation_label(reservation)
    guest_name = _guest_display_name(target_guest)
    candidate = {
        "reservation_id": reservation.pk,
        "guest_id": target_guest.pk,
        "guest_name": guest_name,
        "reservation_label": reservation_label,
        "match_type": "web_guest_slot",
        "check_in_date": reservation.check_in.isoformat(),
    }

    matches: list[dict] = []
    for idx, person in enumerate(persons):
        matches.append(
            {
                "person_index": idx,
                "person_name": _person_full_name(person),
                "confidence": "high",
                "auto_apply": True,
                "candidates": [candidate],
                "reservation_id": reservation.pk,
                "guest_id": target_guest.pk,
                "guest_name": guest_name,
                "reservation_label": reservation_label,
                "audit_status": "confirmed",
            }
        )
    return matches
