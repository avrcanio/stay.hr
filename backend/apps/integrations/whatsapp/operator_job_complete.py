"""Complete operator WhatsApp document intake: apply, check-in, eVisitor, notifications."""

from __future__ import annotations

import logging
from typing import Any

from apps.integrations.whatsapp.whatsapp_operator_service import GuestNotifyMode

from apps.integrations.evisitor.summary import evisitor_summary_for_reservation
from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.integration_lookup import resolve_whatsapp_integration
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.integrations.whatsapp.whatsapp_operator import operator_name_for_wa_id
from apps.integrations.whatsapp.whatsapp_operator_service import (
    _send_operator_text,
    notify_guest_operator_checkin_complete,
)
from apps.reservations.document_intake_match import match_persons_to_guests
from apps.reservations.document_intake_service import apply_document_intake_job, process_document_intake_job
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    Reservation,
    WhatsAppOperatorSession,
    WhatsAppOperatorSessionStatus,
)
from apps.reservations.reservation_checkin_complete import (
    mark_reservation_checked_in,
    submit_evisitor_for_reservation,
)

logger = logging.getLogger(__name__)

_DEFAULT_OPERATOR_WA_ID = "385998388513"


def _validate_job(job: DocumentIntakeJob) -> None:
    if job.source != DocumentIntakeJobSource.WHATSAPP_OPERATOR:
        raise ValueError(f"Job #{job.pk} is not whatsapp_operator source")
    if job.status not in {
        DocumentIntakeJobStatus.DONE,
        DocumentIntakeJobStatus.APPLIED,
    }:
        raise ValueError(f"Job #{job.pk} status={job.status} is not ready for apply")
    persons = (job.ocr_result or {}).get("persons") or []
    if not persons:
        raise ValueError(f"Job #{job.pk} has no OCR persons")
    if job.images.count() == 0:
        raise ValueError(f"Job #{job.pk} has no images")


def _ensure_job_ocr_ready(job: DocumentIntakeJob) -> None:
    if job.status in {
        DocumentIntakeJobStatus.QUEUED,
        DocumentIntakeJobStatus.PROCESSING,
    } or not (job.ocr_result or {}).get("persons"):
        process_document_intake_job(job.pk)
        job.refresh_from_db()
    _validate_job(job)


def _rematch_job(job: DocumentIntakeJob) -> list[dict]:
    persons = (job.ocr_result or {}).get("persons") or []
    matches = match_persons_to_guests(tenant_id=job.tenant_id, persons=persons)
    job.matches = matches
    job.save(update_fields=["matches", "updated_at"])
    return matches


def _reservation_ids_from_auto_matches(matches: list[dict]) -> set[int]:
    ids: set[int] = set()
    for match in matches:
        if not isinstance(match, dict) or not match.get("auto_apply"):
            continue
        rid = match.get("reservation_id")
        if rid is not None:
            ids.add(int(rid))
    return ids


def _build_selections_for_reservation(
    reservation: Reservation,
    matches: list[dict],
) -> list[dict[str, Any]]:
    selections: list[dict[str, Any]] = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        idx = int(match.get("person_index", -1))
        if idx < 0:
            continue
        if match.get("auto_apply") and int(match.get("reservation_id") or 0) == reservation.pk:
            selections.append(
                {
                    "person_index": idx,
                    "reservation_id": reservation.pk,
                    "guest_id": int(match["guest_id"]),
                }
            )
            continue
        candidates = [
            c
            for c in (match.get("candidates") or [])
            if isinstance(c, dict) and int(c.get("reservation_id") or 0) == reservation.pk
        ]
        if not candidates:
            continue
        name_candidates = [c for c in candidates if c.get("match_type") in {"name", "document_number"}]
        pick = name_candidates[0] if name_candidates else candidates[0]
        selections.append(
            {
                "person_index": idx,
                "reservation_id": reservation.pk,
                "guest_id": int(pick["guest_id"]),
            }
        )
    return selections


def _format_operator_success_message(
    *,
    reservation: Reservation,
    operator_name: str,
    applied: list[dict],
    guest_notify: dict,
    evisitor_results: list[dict],
) -> str:
    guest_name = ", ".join(
        str(item.get("guest_name") or "").strip()
        for item in applied
        if isinstance(item, dict) and item.get("guest_name")
    )
    lines = [
        f"Check-in obavljen, {operator_name}.",
        f"Rezervacija #{reservation.pk} ({reservation.booking_code or reservation.external_id})",
        f"Gost: {guest_name or reservation.booker_name}",
        f"Objekt: {reservation.property.name}",
        f"Datumi: {reservation.check_in:%d.%m.%Y} – {reservation.check_out:%d.%m.%Y}",
    ]
    channel = guest_notify.get("channel")
    if channel == "whatsapp":
        lines.append("WhatsApp gostu poslan.")
    elif channel == "email" and guest_notify.get("sent"):
        lines.append(f"Email gostu poslan na {guest_notify.get('to')}.")
    elif guest_notify.get("status") == "already_sent":
        lines.append("Obavijest gostu već poslana.")
    else:
        reason = guest_notify.get("reason") or "nije poslana"
        lines.append(f"Obavijest gostu nije poslana ({reason}).")

    ok_evisitor_statuses = {"not_required", "sent", "SENT"}
    failed_evisitor = [
        r for r in evisitor_results
        if str(r.get("status") or "") not in ok_evisitor_statuses
    ]
    evisitor_ok = evisitor_summary_for_reservation(reservation) == "complete"
    if evisitor_ok:
        lines.append("eVisitor: svi odrasli gosti prijavljeni.")
    elif failed_evisitor:
        lines.append("eVisitor: nije sve uspjelo — provjeri u recepciji.")
        for item in failed_evisitor[:3]:
            name = item.get("guest_name") or f"guest #{item.get('guest_id')}"
            lines.append(f"  • {name}: {item.get('status')} — {item.get('message', '')[:80]}")

    return "\n".join(lines)


def _notify_operator(
    *,
    operator_wa_id: str,
    body: str,
    reservation: Reservation,
    integration_row: IntegrationConfig | None = None,
    runtime: WhatsAppRuntimeConfig | None = None,
) -> dict:
    if integration_row is None or runtime is None:
        integration_row, runtime = resolve_whatsapp_integration(reservation.tenant)
    if integration_row is None or runtime is None:
        return {"status": "skipped", "reason": "no_whatsapp_integration"}
    return _send_operator_text(
        integration_row=integration_row,
        runtime=runtime,
        operator_wa_id=operator_wa_id,
        body=body,
        reservation=reservation,
    )


def complete_operator_checkin_after_apply(
    *,
    job: DocumentIntakeJob,
    reservation: Reservation,
    operator_wa_id: str,
    applied: list[dict],
    integration_row: IntegrationConfig | None = None,
    runtime: WhatsAppRuntimeConfig | None = None,
    session: WhatsAppOperatorSession | None = None,
    guest_notify_mode: GuestNotifyMode = "default",
    time_stay_from: str | None = None,
) -> dict:
    """Check-in status, eVisitor, guest notify (WA-first), Toni confirmation."""
    checkin_result = mark_reservation_checked_in(reservation)
    if checkin_result.get("status") == "blocked":
        message = checkin_result.get("message") or "Check-in nije moguć."
        body = f"Check-in nije moguć.\n{message}"
        _notify_operator(
            operator_wa_id=operator_wa_id,
            body=body,
            reservation=reservation,
            integration_row=integration_row,
            runtime=runtime,
        )
        if session is not None:
            session.status = WhatsAppOperatorSessionStatus.FAILED
            session.save(update_fields=["status", "updated_at"])
        return {
            "status": "checkin_blocked",
            "job_id": job.pk,
            "reservation_id": reservation.pk,
            "checkin": checkin_result,
        }

    reservation.refresh_from_db()
    evisitor_results = submit_evisitor_for_reservation(reservation, time_stay_from=time_stay_from)
    reservation.refresh_from_db()

    guest_notify = notify_guest_operator_checkin_complete(
        reservation,
        guest_notify_mode=guest_notify_mode,
    )

    operator_name = operator_name_for_wa_id(tenant_id=job.tenant_id, wa_id=operator_wa_id) or "Operator"
    success_body = _format_operator_success_message(
        reservation=reservation,
        operator_name=operator_name,
        applied=applied,
        guest_notify=guest_notify,
        evisitor_results=evisitor_results,
    )
    operator_notify = _notify_operator(
        operator_wa_id=operator_wa_id,
        body=success_body,
        reservation=reservation,
        integration_row=integration_row,
        runtime=runtime,
    )

    if session is not None:
        session.status = WhatsAppOperatorSessionStatus.DONE
        session.save(update_fields=["status", "updated_at"])

    return {
        "status": "completed",
        "job_id": job.pk,
        "reservation_id": reservation.pk,
        "applied": applied,
        "checkin": checkin_result,
        "evisitor": evisitor_results,
        "evisitor_summary": evisitor_summary_for_reservation(reservation),
        "guest_notify": guest_notify,
        "operator_whatsapp": operator_notify,
    }


def complete_operator_document_job(
    job_id: int,
    *,
    reservation_id: int | None = None,
    operator_wa_id: str | None = None,
    dry_run: bool = False,
    guest_notify_mode: GuestNotifyMode = "default",
) -> dict:
    job = DocumentIntakeJob.objects.prefetch_related("images").select_related("tenant").get(pk=job_id)
    _ensure_job_ocr_ready(job)

    matches = _rematch_job(job)
    auto_res_ids = _reservation_ids_from_auto_matches(matches)

    target_reservation_id = reservation_id
    if target_reservation_id is None:
        if len(auto_res_ids) == 1:
            target_reservation_id = next(iter(auto_res_ids))
        else:
            raise ValueError(
                f"Ambiguous reservation match (auto_apply ids={sorted(auto_res_ids)}); pass reservation_id"
            )

    reservation = Reservation.objects.select_related("property", "tenant").get(
        pk=target_reservation_id,
        tenant_id=job.tenant_id,
    )

    persons = (job.ocr_result or {}).get("persons") or []
    if not isinstance(persons, list):
        persons = []
    from apps.reservations.guest_slots import ensure_guest_slots_for_intake

    ensure_guest_slots_for_intake(
        tenant=reservation.tenant,
        reservation=reservation,
        min_count=len(persons),
    )
    matches = match_persons_to_guests(
        tenant_id=job.tenant_id,
        persons=persons,
        reservation_id=reservation.pk,
    )
    job.matches = matches
    job.save(update_fields=["matches", "updated_at"])

    selections = _build_selections_for_reservation(reservation, matches)
    if len(selections) != len((job.ocr_result or {}).get("persons") or []):
        raise ValueError(
            f"Could not map all OCR persons to reservation #{target_reservation_id} "
            f"(selections={len(selections)})"
        )

    operator_wa = (operator_wa_id or "").strip() or _DEFAULT_OPERATOR_WA_ID
    session = (
        WhatsAppOperatorSession.objects.filter(job_id=job.pk).order_by("-last_activity_at").first()
    )

    plan = {
        "job_id": job.pk,
        "reservation_id": reservation.pk,
        "selections": selections,
        "matches": matches,
        "operator_wa_id": operator_wa,
        "image_count": job.images.count(),
    }

    if dry_run:
        return {"status": "dry_run", **plan}

    job.reservation_id = reservation.pk
    job.save(update_fields=["reservation_id", "updated_at"])

    applied = apply_document_intake_job(job.pk, selections=selections, whatsapp_reply=False)
    if not applied:
        raise ValueError(f"Apply did not update any guests for job #{job.pk}")

    result = complete_operator_checkin_after_apply(
        job=job,
        reservation=reservation,
        operator_wa_id=operator_wa,
        applied=applied,
        session=session,
        guest_notify_mode=guest_notify_mode,
    )
    return result
