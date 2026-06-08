from __future__ import annotations

import logging
import mimetypes
import re
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.communications.guest_compose import render_checkin_ready_message
from apps.communications.guest_message_send import default_email_subject, send_guest_text_email
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.client import (
    WhatsAppApiError,
    extract_outbound_wamid,
    send_interactive_button_message,
    send_text_message,
)
from apps.integrations.whatsapp.media_download import (
    WhatsAppMediaError,
    extract_media_from_message,
    fetch_whatsapp_media,
)
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.integrations.whatsapp.whatsapp_operator import operator_name_for_wa_id
from apps.reservations.document_intake_service import apply_document_intake_job, process_document_intake_job
from apps.reservations.models import (
    DocumentIntakeImage,
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    Reservation,
    WhatsAppOperatorSession,
    WhatsAppOperatorSessionStatus,
)

logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(minutes=30)
_MEDIA_MESSAGE_TYPES = frozenset({"image", "document"})
_CHECKIN_COMMANDS = frozenset({"check in", "checkin"})
OPERATOR_CHECKIN_BUTTON_ID = "op_check_in"
OPERATOR_CHECKIN_BUTTON_TITLE = "Check-in"


def _normalize_command(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = re.sub(r"[_\-]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def is_operator_checkin_command(text: str) -> bool:
    return _normalize_command(text) in _CHECKIN_COMMANDS


def is_operator_checkin_trigger(*, button_id: str = "", text: str = "") -> bool:
    if (button_id or "").strip() == OPERATOR_CHECKIN_BUTTON_ID:
        return True
    return is_operator_checkin_command(text)


def _image_count_label(count: int) -> str:
    if count == 1:
        return "1 slika"
    if 2 <= count <= 4:
        return f"{count} slike"
    return f"{count} slika"


def _checkin_prompt_body(image_count: int) -> str:
    return (
        f"Primljeno {_image_count_label(image_count)}. "
        f"Pritisnite {OPERATOR_CHECKIN_BUTTON_TITLE} ako ste gotovi."
    )


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


def _session_expired(session: WhatsAppOperatorSession) -> bool:
    return session.last_activity_at + SESSION_TTL < timezone.now()


def _get_collecting_session(
    *,
    tenant_id: int,
    operator_wa_id: str,
) -> WhatsAppOperatorSession | None:
    session = (
        WhatsAppOperatorSession.objects.filter(
            tenant_id=tenant_id,
            operator_wa_id=operator_wa_id,
            status=WhatsAppOperatorSessionStatus.COLLECTING,
        )
        .select_related("job")
        .order_by("-last_activity_at", "id")
        .first()
    )
    if session is None:
        return None
    if _session_expired(session):
        session.status = WhatsAppOperatorSessionStatus.FAILED
        session.save(update_fields=["status", "updated_at"])
        return None
    return session


def _send_operator_text(
    *,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    operator_wa_id: str,
    body: str,
    reservation: Reservation | None = None,
) -> dict:
    try:
        response = send_text_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=operator_wa_id,
            body=body,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        logger.warning("Operator WhatsApp reply failed wa_id=%s: %s", operator_wa_id, exc)
        return {"status": "send_failed", "detail": str(exc)}

    outbound_wamid = extract_outbound_wamid(response)
    if outbound_wamid:
        WhatsAppMessage.objects.create(
            tenant_id=integration_row.tenant_id,
            integration=integration_row,
            reservation=reservation,
            wamid=outbound_wamid,
            wa_id=operator_wa_id,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="text",
            body=body,
            raw_payload=response,
        )
    return {"status": "sent", "outbound_wamid": outbound_wamid}


def _send_operator_checkin_prompt(
    *,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    operator_wa_id: str,
    image_count: int,
) -> dict:
    body = _checkin_prompt_body(image_count)
    try:
        response = send_interactive_button_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=operator_wa_id,
            body=body,
            buttons=[(OPERATOR_CHECKIN_BUTTON_ID, OPERATOR_CHECKIN_BUTTON_TITLE)],
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        logger.warning("Operator check-in prompt failed wa_id=%s: %s", operator_wa_id, exc)
        return {"status": "send_failed", "detail": str(exc)}

    outbound_wamid = extract_outbound_wamid(response)
    if outbound_wamid:
        WhatsAppMessage.objects.create(
            tenant_id=integration_row.tenant_id,
            integration=integration_row,
            wamid=outbound_wamid,
            wa_id=operator_wa_id,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="interactive",
            body=body,
            raw_payload=response,
        )
    return {"status": "sent", "outbound_wamid": outbound_wamid}


def _operator_help_text() -> str:
    return (
        "Operatorski check-in:\n"
        "1) Pošaljite slike dokumenata (osobna/putovnica).\n"
        f"2) Pritisnite gumb {OPERATOR_CHECKIN_BUTTON_TITLE} kad ste gotovi.\n\n"
        "Sustav pronađe rezervaciju, popuni gosta i pošalje potvrdu gostu na email."
    )


def _send_guest_checkin_ready_email(reservation: Reservation) -> dict:
    body = render_checkin_ready_message(reservation)
    subject = default_email_subject(reservation)
    result = send_guest_text_email(reservation, body, subject=subject)
    if not result.get("sent"):
        return result

    sent_at = timezone.now()
    draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.REPLY,
        hint="checkin ready",
        language="",
        llm_body_text=body,
        final_body_text=body,
        channel=GuestMessageChannel.EMAIL,
        sent_at=sent_at,
    )
    GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.EMAIL,
        body_text=body,
        status=GuestOutboundMessageStatus.SENT,
        to_email=result.get("to") or "",
    )
    return result


def _collect_operator_image(
    *,
    row: WhatsAppMessage,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
) -> dict:
    media_id, mime_type, caption = extract_media_from_message(row.raw_payload or {})
    if not media_id:
        return {"status": "skipped", "reason": "no_media_id"}

    try:
        content, downloaded_mime = fetch_whatsapp_media(
            media_id=media_id,
            api_key=runtime.access_token,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppMediaError as exc:
        logger.warning("Operator media download failed message_id=%s: %s", row.pk, exc)
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body=f"Preuzimanje slike nije uspjelo: {exc}",
        )
        return {"status": "download_failed", "detail": str(exc)}

    mime = downloaded_mime or mime_type
    filename = f"op_{row.pk}{_extension_for_mime(mime)}"

    with transaction.atomic():
        session = _get_collecting_session(tenant_id=row.tenant_id, operator_wa_id=row.wa_id)
        if session is None:
            job = DocumentIntakeJob.objects.create(
                tenant_id=row.tenant_id,
                source=DocumentIntakeJobSource.WHATSAPP_OPERATOR,
                status=DocumentIntakeJobStatus.QUEUED,
                device_id="whatsapp_operator",
                whatsapp_message=row,
            )
            session = WhatsAppOperatorSession.objects.create(
                tenant_id=row.tenant_id,
                operator_wa_id=row.wa_id,
                job=job,
                status=WhatsAppOperatorSessionStatus.COLLECTING,
            )
        else:
            job = session.job

        sort_order = job.images.count()
        DocumentIntakeImage.objects.create(
            tenant_id=row.tenant_id,
            job=job,
            image=ContentFile(content, name=filename),
            sort_order=sort_order,
        )
        session.last_activity_at = timezone.now()
        session.save(update_fields=["last_activity_at", "updated_at"])
        if caption and not (row.body or "").strip():
            row.body = caption
            row.save(update_fields=["body"])

    image_count = job.images.count()
    _send_operator_checkin_prompt(
        integration_row=integration_row,
        runtime=runtime,
        operator_wa_id=row.wa_id,
        image_count=image_count,
    )
    return {
        "status": "collected",
        "session_id": session.pk,
        "job_id": job.pk,
        "image_count": image_count,
    }


def _format_match_candidates(matches: list[dict]) -> str:
    lines: list[str] = []
    seen: set[tuple[int, str]] = set()
    for match in matches:
        if not isinstance(match, dict):
            continue
        reservation_id = match.get("reservation_id")
        label = str(match.get("reservation_label") or "").strip()
        if reservation_id is None:
            continue
        key = (int(reservation_id), label)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"• #{reservation_id} {label}".strip())
    return "\n".join(lines[:8])


def _finalize_operator_checkin(
    *,
    row: WhatsAppMessage,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
) -> dict:
    session = _get_collecting_session(tenant_id=row.tenant_id, operator_wa_id=row.wa_id)
    if session is None:
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body="Nema aktivnih slika. Prvo pošaljite fotografije dokumenta.",
        )
        return {"status": "no_session"}

    job = session.job
    if job.images.count() == 0:
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body="Nema slika u sesiji. Pošaljite fotografije dokumenta pa check-in.",
        )
        return {"status": "no_images"}

    session.status = WhatsAppOperatorSessionStatus.PROCESSING
    session.save(update_fields=["status", "updated_at"])

    process_document_intake_job(job.pk)
    job.refresh_from_db()

    if job.status == DocumentIntakeJobStatus.FAILED:
        session.status = WhatsAppOperatorSessionStatus.FAILED
        session.save(update_fields=["status", "updated_at"])
        detail = (job.error_message or "OCR nije uspio.").strip()
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body=f"Check-in nije uspio.\n{detail}",
        )
        return {"status": "ocr_failed", "job_id": job.pk}

    auto_matches = [
        m
        for m in (job.matches or [])
        if isinstance(m, dict) and m.get("auto_apply") and m.get("guest_id")
    ]
    reservation_ids = {int(m["reservation_id"]) for m in auto_matches if m.get("reservation_id")}

    if not auto_matches:
        candidates = _format_match_candidates(job.matches or [])
        body = "Nisam pronašao jednoznačnu rezervaciju."
        if candidates:
            body += f"\n\nKandidati:\n{candidates}"
        session.status = WhatsAppOperatorSessionStatus.FAILED
        session.save(update_fields=["status", "updated_at"])
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body=body,
        )
        return {"status": "no_match", "job_id": job.pk}

    if len(reservation_ids) != 1:
        labels = _format_match_candidates(auto_matches)
        session.status = WhatsAppOperatorSessionStatus.FAILED
        session.save(update_fields=["status", "updated_at"])
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body=f"Više mogućih rezervacija — pojašnjenje ručno u recepciji.\n{labels}",
        )
        return {"status": "ambiguous", "job_id": job.pk}

    reservation_id = next(iter(reservation_ids))
    job.reservation_id = reservation_id
    job.save(update_fields=["reservation_id", "updated_at"])

    try:
        applied = apply_document_intake_job(job.pk)
    except Exception as exc:
        logger.warning("Operator apply failed job_id=%s: %s", job.pk, exc)
        session.status = WhatsAppOperatorSessionStatus.FAILED
        session.save(update_fields=["status", "updated_at"])
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body=f"Apply nije uspio: {exc}",
        )
        return {"status": "apply_failed", "job_id": job.pk}

    if not applied:
        session.status = WhatsAppOperatorSessionStatus.FAILED
        session.save(update_fields=["status", "updated_at"])
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body="Apply nije primijenio podatke gosta.",
        )
        return {"status": "nothing_applied", "job_id": job.pk}

    reservation = Reservation.objects.select_related("property").get(pk=reservation_id)
    email_result = _send_guest_checkin_ready_email(reservation)

    operator_name = operator_name_for_wa_id(tenant_id=row.tenant_id, wa_id=row.wa_id)
    guest_name = ", ".join(
        str(item.get("guest_name") or "").strip()
        for item in applied
        if isinstance(item, dict) and item.get("guest_name")
    )
    success_lines = [
        f"Check-in obavljen, {operator_name}.",
        f"Rezervacija #{reservation.pk} ({reservation.booking_code or reservation.external_id})",
        f"Gost: {guest_name or reservation.booker_name}",
        f"Objekt: {reservation.property.name}",
        f"Datumi: {reservation.check_in:%d.%m.%Y} – {reservation.check_out:%d.%m.%Y}",
    ]
    if email_result.get("sent"):
        success_lines.append(f"Email gostu poslan na {email_result.get('to')}.")
    else:
        success_lines.append(
            "Email gostu nije poslan "
            f"({email_result.get('reason') or 'nema adrese'})."
        )

    session.status = WhatsAppOperatorSessionStatus.DONE
    session.save(update_fields=["status", "updated_at"])
    _send_operator_text(
        integration_row=integration_row,
        runtime=runtime,
        operator_wa_id=row.wa_id,
        body="\n".join(success_lines),
        reservation=reservation,
    )
    return {
        "status": "completed",
        "job_id": job.pk,
        "reservation_id": reservation_id,
        "email": email_result,
    }


def handle_operator_inbound(
    *,
    row: WhatsAppMessage,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    action_text: str,
    button_id: str = "",
) -> dict:
    if row.message_type in _MEDIA_MESSAGE_TYPES:
        return _collect_operator_image(
            row=row,
            integration_row=integration_row,
            runtime=runtime,
        )

    if is_operator_checkin_trigger(button_id=button_id, text=action_text):
        return _finalize_operator_checkin(
            row=row,
            integration_row=integration_row,
            runtime=runtime,
        )

    _send_operator_text(
        integration_row=integration_row,
        runtime=runtime,
        operator_wa_id=row.wa_id,
        body=_operator_help_text(),
    )
    return {"status": "help_sent"}
