"""Shared finalize: merge jobs, OCR, completeness audit, apply, check-in branches."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Literal

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.communications.guest_compose import (
    HINT_ID_MISSING_SIDES,
    render_document_intake_incomplete_message,
)
from apps.communications.models import GuestMessageIntent
from apps.core.timezone import property_local_now
from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.apply_reply import _send_whatsapp_text_reply
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.integrations.whatsapp.whatsapp_operator_service import (
    _auto_matches_from_job,
    _reservation_ids_from_auto_matches,
    _send_operator_text,
    merge_images_into_operator_job,
)
from apps.reservations.checkin import validate_reservation_check_in
from apps.reservations.document_intake_context import (
    DocumentIntakeContext,
    ensure_job_tenant_matches_reservation,
)
from apps.reservations.document_intake_completeness import evaluate_completeness
from apps.reservations.document_intake_service import apply_document_intake_job, process_document_intake_job, completeness_to_dict
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    Reservation,
    WhatsAppDocumentBatchSession,
    WhatsAppDocumentBatchStatus,
    WhatsAppOperatorSession,
    WhatsAppOperatorSessionStatus,
)

logger = logging.getLogger(__name__)

_MERGE_WINDOW = timedelta(hours=2)


def _image_filename_in_job(job: DocumentIntakeJob, filename: str) -> bool:
    for img in job.images.only("image"):
        name = (img.image.name or "").rsplit("/", 1)[-1]
        if name == filename:
            return True
    return False


def _copy_image_to_job(
    *,
    tenant_id: int,
    target_job: DocumentIntakeJob,
    source_img: DocumentIntakeImage,
) -> bool:
    name = (source_img.image.name or "").rsplit("/", 1)[-1]
    if _image_filename_in_job(target_job, name):
        return False
    source_img.image.open("rb")
    try:
        content = source_img.image.read()
    finally:
        source_img.image.close()
    sort_order = target_job.images.count()
    DocumentIntakeImage.objects.create(
        tenant_id=tenant_id,
        job=target_job,
        image=ContentFile(content, name=name),
        sort_order=sort_order,
        detected_side=source_img.detected_side,
    )
    return True


def merge_related_whatsapp_jobs(
    ctx: DocumentIntakeContext,
    *,
    channel: Literal["guest", "operator"],
    operator_wa_id: str | None = None,
) -> int:
    """Copy images from parallel recent jobs into the target job (idempotent by filename)."""
    job = ctx.job
    tenant_id = ctx.effective_tenant_id
    since = timezone.now() - _MERGE_WINDOW
    moved = 0

    if channel == "guest" and ctx.is_reservation_scoped:
        other_jobs = DocumentIntakeJob.objects.filter(
            tenant_id=tenant_id,
            reservation_id=job.reservation_id,
            source=DocumentIntakeJobSource.WHATSAPP,
            created_at__gte=since,
        ).exclude(pk=job.pk).prefetch_related("images")

        for other in other_jobs:
            if other.status == DocumentIntakeJobStatus.APPLIED:
                continue
            for img in other.images.order_by("sort_order", "id"):
                if _copy_image_to_job(tenant_id=tenant_id, target_job=job, source_img=img):
                    moved += 1

    elif channel == "operator" and operator_wa_id:
        other_jobs = DocumentIntakeJob.objects.filter(
            tenant_id=tenant_id,
            source=DocumentIntakeJobSource.WHATSAPP_OPERATOR,
            created_at__gte=since,
        ).exclude(pk=job.pk).prefetch_related("images")

        session_job_ids = set(
            WhatsAppOperatorSession.objects.filter(
                tenant_id=tenant_id,
                operator_wa_id=operator_wa_id,
                status__in={
                    WhatsAppOperatorSessionStatus.COLLECTING,
                    WhatsAppOperatorSessionStatus.AWAITING_CONFIRM,
                },
            ).values_list("job_id", flat=True)
        )
        candidates = [j for j in other_jobs if j.pk in session_job_ids or j.status != DocumentIntakeJobStatus.APPLIED]
        moved = merge_images_into_operator_job(job, candidates)

    return moved


def _set_session_collecting(
    session: WhatsAppDocumentBatchSession | WhatsAppOperatorSession,
) -> None:
    if isinstance(session, WhatsAppDocumentBatchSession):
        session.status = WhatsAppDocumentBatchStatus.COLLECTING
        session.save(update_fields=["status", "updated_at"])
    else:
        session.status = WhatsAppOperatorSessionStatus.COLLECTING
        session.last_activity_at = timezone.now()
        session.save(update_fields=["status", "last_activity_at", "updated_at"])


def _send_incomplete_reply(
    *,
    channel: Literal["guest", "operator"],
    job: DocumentIntakeJob,
    reservation: Reservation,
    body: str,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    operator_wa_id: str | None,
) -> dict:
    if channel == "guest":
        return _send_whatsapp_text_reply(
            job=job,
            body=body,
            intent=GuestMessageIntent.REPLY,
            hint=HINT_ID_MISSING_SIDES,
            mark_reply_sent=False,
        )
    return _send_operator_text(
        integration_row=integration_row,
        runtime=runtime,
        operator_wa_id=operator_wa_id or "",
        body=body,
        reservation=reservation,
    )


def finalize_document_intake_job(
    ctx: DocumentIntakeContext,
    *,
    channel: Literal["guest", "operator"],
    wa_id: str,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    session: WhatsAppDocumentBatchSession | WhatsAppOperatorSession,
) -> dict:
    job = ctx.job
    merge_related_whatsapp_jobs(ctx, channel=channel, operator_wa_id=wa_id if channel == "operator" else None)

    process_document_intake_job(ctx)
    job.refresh_from_db()

    if job.status == DocumentIntakeJobStatus.FAILED:
        if channel == "guest":
            from apps.integrations.whatsapp.apply_reply import maybe_send_checkin_automation_failed_whatsapp_reply

            reply = maybe_send_checkin_automation_failed_whatsapp_reply(job)
            return {"status": "ocr_failed", "job_id": job.pk, "reply": reply}
        detail = (job.error_message or "OCR nije uspio.").strip()
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=wa_id,
            body=f"Check-in nije uspio.\n{detail}",
        )
        if isinstance(session, WhatsAppOperatorSession):
            session.status = WhatsAppOperatorSessionStatus.FAILED
            session.save(update_fields=["status", "updated_at"])
        return {"status": "ocr_failed", "job_id": job.pk}

    if channel == "operator":
        auto_matches = _auto_matches_from_job(job)
        reservation_ids = _reservation_ids_from_auto_matches(auto_matches)
        if not auto_matches or len(reservation_ids) != 1:
            return {
                "status": "ambiguous_reservation",
                "job_id": job.pk,
                "reservation_ids": sorted(reservation_ids),
            }

        reservation_id = next(iter(reservation_ids))
        reservation = Reservation.objects.select_related("tenant", "property").get(pk=reservation_id)
        job.reservation_id = reservation_id
        ensure_job_tenant_matches_reservation(job, reservation)
        job.save(update_fields=["reservation_id", "tenant_id", "updated_at"])
        ctx = DocumentIntakeContext.from_job(job)

    if job.reservation_id is None:
        return {"status": "no_reservation", "job_id": job.pk}

    reservation = ctx.reservation or Reservation.objects.select_related("property", "tenant").get(
        pk=job.reservation_id
    )

    if channel == "guest":
        from apps.integrations.whatsapp.guest_document_lifecycle import (
            check_guest_document_intake_automation,
        )

        allowed, reason = check_guest_document_intake_automation(reservation)
        if not allowed:
            return {"status": "skipped", "reason": reason, "job_id": job.pk}

    persons = (job.ocr_result or {}).get("persons") or []
    images = list(job.images.order_by("sort_order", "id"))

    from apps.reservations.document_intake_audit import rematch_and_audit_job

    matches = rematch_and_audit_job(ctx)

    completeness = evaluate_completeness(
        reservation=reservation,
        persons=persons,
        matches=matches,
        images=images,
    )

    if not completeness.is_complete:
        try:
            apply_document_intake_job(ctx, whatsapp_reply=False, allow_partial=True)
            job.refresh_from_db()
        except Exception as exc:
            logger.warning("Document finalize partial apply failed job_id=%s: %s", job.pk, exc)

        completeness = evaluate_completeness(
            reservation=reservation,
            persons=persons,
            matches=matches,
            images=images,
        )

    if not completeness.is_complete:
        body = render_document_intake_incomplete_message(
            reservation, completeness, image_count=len(images),
        )
        _set_session_collecting(session)
        reply = _send_incomplete_reply(
            channel=channel,
            job=job,
            reservation=reservation,
            body=body,
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=wa_id,
        )
        return {
            "status": "incomplete",
            "job_id": job.pk,
            "reservation_id": reservation.pk,
            "reply": reply,
            "completeness": completeness_to_dict(completeness),
        }

    processing_at = property_local_now(reservation.property)
    time_stay_from = processing_at.strftime("%H:%M")

    try:
        applied = apply_document_intake_job(ctx, whatsapp_reply=False)
    except Exception as exc:
        logger.warning("Document finalize apply failed job_id=%s: %s", job.pk, exc)
        if channel == "operator":
            _send_operator_text(
                integration_row=integration_row,
                runtime=runtime,
                operator_wa_id=wa_id,
                body=f"Apply nije uspio: {exc}",
                reservation=reservation,
            )
            if isinstance(session, WhatsAppOperatorSession):
                session.status = WhatsAppOperatorSessionStatus.FAILED
                session.save(update_fields=["status", "updated_at"])
        return {"status": "apply_failed", "job_id": job.pk, "detail": str(exc)[:200]}

    if not applied:
        if channel == "operator":
            _send_operator_text(
                integration_row=integration_row,
                runtime=runtime,
                operator_wa_id=wa_id,
                body="Apply nije primijenio podatke gosta.",
                reservation=reservation,
            )
            if isinstance(session, WhatsAppOperatorSession):
                session.status = WhatsAppOperatorSessionStatus.FAILED
                session.save(update_fields=["status", "updated_at"])
        return {"status": "nothing_applied", "job_id": job.pk}

    reservation.refresh_from_db()
    today = property_local_now(reservation.property).date()
    is_check_in_day = today == reservation.check_in

    if channel == "operator":
        from apps.integrations.whatsapp.operator_job_complete import complete_operator_checkin_after_apply

        return complete_operator_checkin_after_apply(
            job=job,
            reservation=reservation,
            operator_wa_id=wa_id,
            applied=applied,
            integration_row=integration_row,
            runtime=runtime,
            session=session if isinstance(session, WhatsAppOperatorSession) else None,
            time_stay_from=time_stay_from,
        )

    # Guest channel: same-day arrival → docs saved + awaiting Toni; before arrival → checkin_ready message
    if is_check_in_day:
        from apps.integrations.whatsapp.guest_docs_awaiting_arrival import notify_guest_docs_awaiting_arrival

        guest_notify = notify_guest_docs_awaiting_arrival(reservation)
        if isinstance(session, WhatsAppDocumentBatchSession):
            session.status = WhatsAppDocumentBatchStatus.DONE
            session.save(update_fields=["status", "updated_at"])
        return {
            "status": "docs_awaiting_arrival",
            "job_id": job.pk,
            "reservation_id": reservation.pk,
            "applied": applied,
            "guest_notify": guest_notify,
        }

    from apps.integrations.whatsapp.apply_reply import maybe_send_document_apply_whatsapp_reply

    reply = maybe_send_document_apply_whatsapp_reply(ctx, applied=applied)
    if isinstance(session, WhatsAppDocumentBatchSession):
        session.status = WhatsAppDocumentBatchStatus.DONE
        session.save(update_fields=["status", "updated_at"])
    return {
        "status": "docs_saved",
        "job_id": job.pk,
        "reservation_id": reservation.pk,
        "applied": applied,
        "reply": reply,
    }
