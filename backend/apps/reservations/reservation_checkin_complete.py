"""Shared check-in, eVisitor submission, and guest notification after document apply."""

from __future__ import annotations

import logging
from typing import Any

from apps.integrations.evisitor.eligibility import guest_requires_evisitor
from apps.integrations.evisitor.exceptions import (
    EvisitorApiError,
    EvisitorConfigError,
    EvisitorValidationError,
)
from apps.integrations.evisitor.service import submit_guest_checkin
from apps.integrations.evisitor.summary import evisitor_summary_for_reservation
from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.apply_reply import is_document_checkin_complete
from apps.integrations.whatsapp.guest_docs_awaiting_arrival import docs_awaiting_arrival_already_sent
from apps.integrations.whatsapp.integration_lookup import resolve_whatsapp_integration
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.integrations.whatsapp.whatsapp_operator import operator_name_for_wa_id
from apps.integrations.whatsapp.whatsapp_operator_service import (
    _send_operator_text,
    notify_guest_operator_checkin_complete,
)
from apps.reservations.checkin import CheckInBlockedError, validate_reservation_check_in
from apps.reservations.models import DocumentIntakeJob, Reservation

logger = logging.getLogger(__name__)


def mark_reservation_checked_in(reservation: Reservation) -> dict:
    if reservation.status == Reservation.Status.CHECKED_IN:
        return {"status": "already_checked_in"}

    tenant = reservation.tenant
    try:
        validate_reservation_check_in(reservation, tenant=tenant)
    except CheckInBlockedError as exc:
        return {"status": "blocked", "code": exc.code, "message": exc.message}

    old_status = reservation.status
    reservation.status = Reservation.Status.CHECKED_IN
    reservation.save(update_fields=["status", "updated_at"])

    from apps.integrations.whatsapp.apply_reply import waive_whatsapp_autocheckin

    waive_whatsapp_autocheckin(reservation)

    from apps.core.tasks import notify_reservation_status_changed

    notify_reservation_status_changed.delay(
        reservation.pk,
        old_status,
        reservation.status,
    )
    return {"status": "checked_in", "old_status": old_status}


def submit_evisitor_for_reservation(
    reservation: Reservation,
    *,
    time_stay_from: str | None = None,
) -> list[dict]:
    results: list[dict] = []
    guests = list(reservation.guests.all())
    for guest in guests:
        if not guest_requires_evisitor(guest, reference_date=reservation.check_in):
            results.append(
                {
                    "guest_id": guest.pk,
                    "guest_name": guest.name or f"{guest.first_name} {guest.last_name}".strip(),
                    "status": "not_required",
                }
            )
            continue
        try:
            submission = submit_guest_checkin(guest, time_stay_from=time_stay_from)
            results.append(
                {
                    "guest_id": guest.pk,
                    "guest_name": guest.name or f"{guest.first_name} {guest.last_name}".strip(),
                    "status": submission.status,
                    "registration_id": str(submission.registration_id),
                }
            )
        except EvisitorValidationError as exc:
            results.append(
                {
                    "guest_id": guest.pk,
                    "guest_name": guest.name or f"{guest.first_name} {guest.last_name}".strip(),
                    "status": "validation_failed",
                    "message": str(exc),
                    "field_errors": exc.field_errors or {},
                }
            )
        except EvisitorConfigError as exc:
            results.append(
                {
                    "guest_id": guest.pk,
                    "status": "config_error",
                    "message": str(exc),
                }
            )
        except EvisitorApiError as exc:
            results.append(
                {
                    "guest_id": guest.pk,
                    "status": "api_error",
                    "message": str(exc),
                }
            )
    return results


def complete_guest_checkin_after_apply(
    *,
    job: DocumentIntakeJob,
    reservation: Reservation,
    applied: list[dict[str, Any]],
    time_stay_from: str | None = None,
) -> dict:
    """Mark checked-in, submit eVisitor, notify guest (idempotent if already checked-in)."""
    if reservation.status == Reservation.Status.CHECKED_IN:
        reservation.refresh_from_db()
        guest_notify = notify_guest_operator_checkin_complete(reservation)
        return {
            "status": "already_checked_in",
            "job_id": job.pk,
            "reservation_id": reservation.pk,
            "applied": applied,
            "checkin": {"status": "already_checked_in"},
            "guest_notify": guest_notify,
        }

    checkin_result = mark_reservation_checked_in(reservation)
    if checkin_result.get("status") == "blocked":
        logger.warning(
            "Deferred guest check-in blocked reservation_id=%s code=%s",
            reservation.pk,
            checkin_result.get("code"),
        )
        from apps.core.tasks import notify_guest_message_inbound

        notify_guest_message_inbound.delay(
            reservation.pk,
            channel="whatsapp",
            body_preview="Check-in blokiran — dokumenti spremljeni, recepcija provjerava",
        )
        return {
            "status": "checkin_blocked",
            "job_id": job.pk,
            "reservation_id": reservation.pk,
            "applied": applied,
            "checkin": checkin_result,
        }

    reservation.refresh_from_db()
    evisitor_results = submit_evisitor_for_reservation(reservation, time_stay_from=time_stay_from)
    reservation.refresh_from_db()
    guest_notify = notify_guest_operator_checkin_complete(reservation)

    return {
        "status": "completed",
        "job_id": job.pk,
        "reservation_id": reservation.pk,
        "applied": applied,
        "checkin": checkin_result,
        "evisitor": evisitor_results,
        "evisitor_summary": evisitor_summary_for_reservation(reservation),
        "guest_notify": guest_notify,
    }


def perform_arrival_confirmed_checkin(
    reservation: Reservation,
    *,
    time_stay_from: str | None,
    operator_wa_id: str,
    confirmed_arrival_at=None,
    integration_row: IntegrationConfig | None = None,
    runtime: WhatsAppRuntimeConfig | None = None,
) -> dict:
    """Toni-confirmed arrival: check-in + eVisitor; skip guest complete if docs-awaiting already sent."""
    if integration_row is None or runtime is None:
        integration_row, runtime = resolve_whatsapp_integration(reservation.tenant)

    checkin_result = mark_reservation_checked_in(reservation)
    if checkin_result.get("status") == "blocked":
        message = checkin_result.get("message") or "Check-in nije moguć."
        if integration_row is not None and runtime is not None:
            _send_operator_text(
                integration_row=integration_row,
                runtime=runtime,
                operator_wa_id=operator_wa_id,
                body=f"Check-in nije moguć.\n{message}",
                reservation=reservation,
            )
        return {
            "status": "checkin_blocked",
            "reservation_id": reservation.pk,
            "checkin": checkin_result,
        }

    reservation.refresh_from_db()
    evisitor_results = submit_evisitor_for_reservation(reservation, time_stay_from=time_stay_from)
    reservation.refresh_from_db()

    guest_notify: dict
    if docs_awaiting_arrival_already_sent(reservation):
        guest_notify = {"channel": "none", "status": "already_sent", "reason": "docs_awaiting_arrival"}
    else:
        guest_notify = notify_guest_operator_checkin_complete(reservation)

    from apps.integrations.whatsapp.operator_job_complete import _format_operator_success_message

    operator_name = operator_name_for_wa_id(tenant_id=reservation.tenant_id, wa_id=operator_wa_id) or "Operator"
    success_body = _format_operator_success_message(
        reservation=reservation,
        operator_name=operator_name,
        applied=[],
        guest_notify=guest_notify,
        evisitor_results=evisitor_results,
    )
    if not is_document_checkin_complete(reservation):
        success_body += "\n\nCheck-in OK — dokumenti nisu kompletni, slikaj dokumente ručno."
    failed_evisitor = [
        r
        for r in evisitor_results
        if str(r.get("status") or "") not in {"not_required", "sent", "SENT"}
    ]
    if failed_evisitor:
        success_body += "\neVisitor: nije sve uspjelo — provjeri u recepciji."

    operator_notify: dict = {"status": "skipped", "reason": "no_integration"}
    if integration_row is not None and runtime is not None:
        operator_notify = _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=operator_wa_id,
            body=success_body,
            reservation=reservation,
        )

    return {
        "status": "completed",
        "reservation_id": reservation.pk,
        "checkin": checkin_result,
        "evisitor": evisitor_results,
        "evisitor_summary": evisitor_summary_for_reservation(reservation),
        "guest_notify": guest_notify,
        "operator_whatsapp": operator_notify,
        "confirmed_arrival_at": confirmed_arrival_at.isoformat() if confirmed_arrival_at else None,
    }
