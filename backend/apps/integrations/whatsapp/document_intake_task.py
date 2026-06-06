from __future__ import annotations

import logging
import mimetypes

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction

from apps.integrations.models import WhatsAppMessage
from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.integrations.whatsapp.media_download import (
    WhatsAppMediaError,
    extract_media_from_message,
    fetch_whatsapp_media,
)
from apps.integrations.whatsapp.reservation_lookup import find_reservation_for_wa_id
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.reservations.document_intake_service import apply_document_intake_job, process_document_intake_job
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
)

logger = logging.getLogger(__name__)

_MEDIA_MESSAGE_TYPES = frozenset({"image", "document"})


def _extension_for_mime(mime_type: str) -> str:
    ext = mimetypes.guess_extension(mime_type.split(";")[0].strip()) or ""
    if ext == ".jpe":
        ext = ".jpg"
    if ext:
        return ext
    if mime_type.startswith("image/"):
        return ".jpg"
    if mime_type == "application/pdf":
        return ".pdf"
    return ".bin"


@shared_task
def process_whatsapp_document_message(message_id: int) -> dict:
    row = (
        WhatsAppMessage.objects.select_related("integration", "tenant", "reservation")
        .filter(pk=message_id, direction=WhatsAppMessage.Direction.INBOUND)
        .first()
    )
    if row is None:
        return {"status": "missing"}

    if row.message_type not in _MEDIA_MESSAGE_TYPES:
        return {"status": "skipped", "reason": "not_media"}

    media_id, mime_type, caption = extract_media_from_message(row.raw_payload or {})
    if not media_id:
        return {"status": "skipped", "reason": "no_media_id"}

    if row.reservation_id is None:
        reservation = find_reservation_for_wa_id(tenant_id=row.tenant_id, wa_id=row.wa_id)
        if reservation is not None:
            row.reservation = reservation
            row.save(update_fields=["reservation"])
    else:
        reservation = row.reservation

    if reservation is None:
        return {"status": "skipped", "reason": "no_reservation"}

    existing = DocumentIntakeJob.objects.filter(
        whatsapp_message_id=row.pk,
        tenant_id=row.tenant_id,
    ).first()
    if existing is not None:
        return {"status": "duplicate", "job_id": existing.pk}

    integration_row, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration_row is None or runtime is None:
        return {"status": "skipped", "reason": "no_integration"}

    try:
        content, downloaded_mime = fetch_whatsapp_media(
            media_id=media_id,
            api_key=runtime.access_token,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppMediaError as exc:
        logger.warning("WhatsApp media download failed message_id=%s: %s", row.pk, exc)
        return {"status": "download_failed", "detail": str(exc)}

    mime = downloaded_mime or mime_type
    filename = f"wa_{row.pk}{_extension_for_mime(mime)}"

    with transaction.atomic():
        job = DocumentIntakeJob.objects.create(
            tenant_id=row.tenant_id,
            reservation=reservation,
            whatsapp_message=row,
            source=DocumentIntakeJobSource.WHATSAPP,
            status=DocumentIntakeJobStatus.QUEUED,
            device_id="whatsapp",
        )
        DocumentIntakeImage.objects.create(
            tenant_id=row.tenant_id,
            job=job,
            image=ContentFile(content, name=filename),
            sort_order=0,
        )
        if caption and not (row.body or "").strip():
            row.body = caption
            row.save(update_fields=["body"])

    process_document_intake_job(job.pk)
    job.refresh_from_db()

    apply_result: dict = {"status": "skipped", "reason": "not_ready"}
    if job.status == DocumentIntakeJobStatus.DONE and any(
        isinstance(m, dict) and m.get("auto_apply") and m.get("guest_id") for m in (job.matches or [])
    ):
        try:
            applied = apply_document_intake_job(job.pk)
            apply_result = {"status": "applied", "guest_ids": [a.get("guest_id") for a in applied]}
        except Exception as exc:
            logger.warning("WhatsApp document auto-apply failed job_id=%s: %s", job.pk, exc)
            apply_result = {"status": "apply_failed", "detail": str(exc)[:200]}

    from apps.core.tasks import notify_guest_message_inbound

    notify_guest_message_inbound.delay(
        reservation.pk,
        channel="whatsapp",
        body_preview="Dokumenti primljeni — pregledaj OCR",
    )

    return {
        "status": "processed",
        "job_id": job.pk,
        "reservation_id": reservation.pk,
        "apply": apply_result,
    }
