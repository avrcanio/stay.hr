"""Read-only lifecycle gate for WhatsApp document intake automation."""

from __future__ import annotations

import logging

from django.conf import settings

from apps.integrations.whatsapp.apply_reply import (
    is_document_checkin_complete,
    is_whatsapp_autocheckin_waived,
)
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)


class LifecycleBlockReason:
    """Standard block reason codes for document intake automation."""

    ALLOWED = ""
    WAIVED = "waived"
    DOCUMENTS_COMPLETE = "documents_complete"
    WEB_CHECKIN_ONLY = "web_checkin_only"
    CHECKED_OUT = "checked_out"
    CANCELED = "canceled"
    NO_SHOW = "no_show"
    REFUSED = "refused"


_TERMINAL_STATUSES = frozenset(
    {
        Reservation.Status.CHECKED_OUT,
        Reservation.Status.CANCELED,
        Reservation.Status.NO_SHOW,
        Reservation.Status.REFUSED,
    }
)

_STATUS_TO_REASON: dict[str, str] = {
    Reservation.Status.CHECKED_OUT: LifecycleBlockReason.CHECKED_OUT,
    Reservation.Status.CANCELED: LifecycleBlockReason.CANCELED,
    Reservation.Status.NO_SHOW: LifecycleBlockReason.NO_SHOW,
    Reservation.Status.REFUSED: LifecycleBlockReason.REFUSED,
}


def whatsapp_document_intake_lifecycle_gate_enabled() -> bool:
    return bool(settings.WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE)


def guest_checkin_web_only_enabled() -> bool:
    return bool(getattr(settings, "GUEST_CHECKIN_WEB_ONLY", True))


def guest_document_intake_automation_allowed(
    reservation: Reservation,
    *,
    block_documents_complete: bool = True,
) -> tuple[bool, str]:
    """Read-only gate: whether document intake automation may run.

    No DB writes and no outbound messages. When the lifecycle gate flag is off,
    terminal reservation statuses are not blocked (legacy behaviour); waived and
    documents-complete checks always apply.
    """
    if guest_checkin_web_only_enabled():
        return False, LifecycleBlockReason.WEB_CHECKIN_ONLY

    if is_whatsapp_autocheckin_waived(reservation):
        return False, LifecycleBlockReason.WAIVED

    if whatsapp_document_intake_lifecycle_gate_enabled():
        if reservation.status in _TERMINAL_STATUSES:
            return False, _STATUS_TO_REASON[reservation.status]

    if block_documents_complete and is_document_checkin_complete(reservation):
        return False, LifecycleBlockReason.DOCUMENTS_COMPLETE

    return True, LifecycleBlockReason.ALLOWED


def check_guest_document_intake_automation(
    reservation: Reservation,
    *,
    block_documents_complete: bool = True,
) -> tuple[bool, str]:
    """Gate plus structured audit log when automation is blocked."""
    allowed, reason = guest_document_intake_automation_allowed(
        reservation,
        block_documents_complete=block_documents_complete,
    )
    if not allowed:
        logger.info(
            "automation_blocked reservation_id=%s reason=%s",
            reservation.pk,
            reason,
        )
    return allowed, reason
