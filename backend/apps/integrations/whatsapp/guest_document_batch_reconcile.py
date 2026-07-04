"""Periodic reconcile for stuck guest WhatsApp document batch sessions."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.integrations.whatsapp.integration_lookup import resolve_whatsapp_integration
from apps.integrations.whatsapp.whatsapp_document_batch import (
    _ACTIVE_STATUSES,
    _prompt_and_await_confirm,
    _run_finalize,
    assess_batch_after_quiet,
)
from apps.reservations.document_intake_audit import rematch_and_audit_job, try_apply_complete_job
from apps.reservations.document_intake_completeness import evaluate_completeness
from apps.reservations.document_intake_service import process_document_intake_job
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    Reservation,
    WhatsAppDocumentBatchSession,
    WhatsAppDocumentBatchStatus,
)

logger = logging.getLogger(__name__)

STUCK_CONFIRM_MINUTES = 10
STUCK_JOB_MINUTES = 5
STUCK_COLLECTING_AFTER_PROMPT_MINUTES = 5


def reconcile_guest_document_batch(
    *,
    reservation_id: int | None = None,
    apply: bool = False,
    re_prompt_confirm: bool = False,
) -> dict:
    """Find stuck guest document batches and attempt heal (rematch, apply, re-prompt)."""
    now = timezone.now()
    results: list[dict] = []

    job_qs = DocumentIntakeJob.objects.filter(
        source=DocumentIntakeJobSource.WHATSAPP,
        status=DocumentIntakeJobStatus.DONE,
        applied_result=[],
        processed_at__lte=now - timedelta(minutes=STUCK_JOB_MINUTES),
    ).select_related("reservation")
    if reservation_id is not None:
        job_qs = job_qs.filter(reservation_id=reservation_id)

    for job in job_qs[:50]:
        if not job.reservation_id:
            continue
        reservation = Reservation.objects.prefetch_related("guests").get(pk=job.reservation_id)
        images = list(job.images.order_by("sort_order", "id"))
        persons = (job.ocr_result or {}).get("persons") or []
        completeness = evaluate_completeness(
            reservation=reservation,
            persons=persons,
            matches=job.matches or [],
            images=images,
        )
        if completeness.ocr_under_extracted:
            process_document_intake_job(job.pk)
            job.refresh_from_db()
            entry: dict = {"job_id": job.pk, "reservation_id": reservation.pk, "action": "re_ocr"}
        else:
            rematch_and_audit_job(job, reservation=reservation)
            entry = {"job_id": job.pk, "reservation_id": reservation.pk, "action": "rematched"}
        if apply:
            applied = try_apply_complete_job(job, reservation=reservation)
            if applied:
                entry["action"] = "applied"
                entry["applied_count"] = len(applied)
        results.append(entry)

    session_qs = WhatsAppDocumentBatchSession.objects.filter(
        status__in=_ACTIVE_STATUSES,
    ).select_related("job", "reservation", "reservation__property", "tenant")
    if reservation_id is not None:
        session_qs = session_qs.filter(reservation_id=reservation_id)

    for session in session_qs[:50]:
        entry = {"session_id": session.pk, "reservation_id": session.reservation_id, "status": session.status}
        if session.status == WhatsAppDocumentBatchStatus.AWAITING_CONFIRM:
            prompt_at = session.prompt_sent_at or session.updated_at
            if prompt_at and prompt_at <= now - timedelta(minutes=STUCK_CONFIRM_MINUTES):
                if re_prompt_confirm:
                    send = _prompt_and_await_confirm(session)
                    entry["action"] = "re_prompt_confirm"
                    entry["send"] = send
                else:
                    integration_row, runtime = resolve_whatsapp_integration(session.tenant)
                    if integration_row and runtime:
                        finalize_result = _run_finalize(session)
                        entry["action"] = "finalize"
                        entry["finalize"] = finalize_result
        elif session.status in {
            WhatsAppDocumentBatchStatus.COLLECTING,
            WhatsAppDocumentBatchStatus.AFTER_NO,
        }:
            job = session.job
            if job and job.status == DocumentIntakeJobStatus.DONE and job.images.exists():
                integration_row, runtime = resolve_whatsapp_integration(session.tenant)
                if integration_row and runtime and apply:
                    finalize_result = _run_finalize(session)
                    entry["action"] = "finalize_collecting"
                    entry["finalize"] = finalize_result
            elif (
                session.status == WhatsAppDocumentBatchStatus.COLLECTING
                and (session.prompt_count or 0) > 0
                and session.last_media_at
                and session.last_media_at <= now - timedelta(minutes=STUCK_COLLECTING_AFTER_PROMPT_MINUTES)
            ):
                integration_row, runtime = resolve_whatsapp_integration(session.tenant)
                if integration_row and runtime:
                    if apply:
                        finalize_result = _run_finalize(session)
                        entry["action"] = "finalize_stuck_collecting"
                        entry["finalize"] = finalize_result
                    else:
                        assess_result = assess_batch_after_quiet(session)
                        entry["action"] = "assess_stuck_collecting"
                        entry["assess"] = assess_result
        if "action" in entry:
            results.append(entry)

    return {"reconciled": len(results), "items": results}


@shared_task
def reconcile_guest_document_batches(
    reservation_id: int | None = None,
    apply: bool = False,
    re_prompt_confirm: bool = False,
) -> dict:
    return reconcile_guest_document_batch(
        reservation_id=reservation_id,
        apply=apply,
        re_prompt_confirm=re_prompt_confirm,
    )
