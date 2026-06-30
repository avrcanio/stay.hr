"""Central guest arrival-time detection, save, and auto-reply (all channels)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Literal

from django.utils import timezone

from apps.ai.provider import GuestComposeError, llm_configured
from apps.communications.guest_arrival_llm import (
    ArrivalLlmResult,
    analyze_and_compose_arrival_reply,
    arrival_llm_audit_fields,
)
from apps.communications.guest_compose import (
    HINT_ARRIVAL_AUTO_REPLY,
    render_arrival_late_inquiry_message,
    render_arrival_time_saved_message,
)
from apps.communications.guest_language_context import LanguageMode
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.communications.guest_arrival_policy import is_late_arrival
from apps.communications.guest_message_send import send_guest_message
from apps.communications.models import GuestMessageChannel, GuestMessageDraft, GuestMessageIntent
from apps.core.timezone import property_local_now
from apps.integrations.whatsapp.arrival_time_parse import parse_guest_stated_arrival
from apps.integrations.whatsapp.whatsapp_post_checkin_reply import guest_message_mentions_arrival
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)

ArrivalInboundKind = Literal["time_stated", "late_inquiry"]

_LATE_INQUIRY = re.compile(
    r"\b("
    r"late|later|kasnij\w*|spät|spat|tard\w*|"
    r"after\s+\d|evening|večer|vecer|noc|night|"
    r"check.?in.*(late|kasn|spät)|"
    r"mogu\s+(li|mo)\s+doći|može\s+li|"
    r"can\s+(we|i)\s+(arrive|check|come)|"
    r"is\s+it\s+possible|possible\s+to\s+(arrive|check)"
    r")\b",
    re.IGNORECASE,
)

_CHANNEL_MAP = {
    "whatsapp": GuestMessageChannel.WHATSAPP,
    "email": GuestMessageChannel.EMAIL,
    "booking": GuestMessageChannel.BOOKING,
}


def classify_inbound(
    body: str,
    reservation: Reservation,
    *,
    reference_at: datetime | None = None,
) -> ArrivalInboundKind | None:
    text = (body or "").strip()
    if not text:
        return None
    if not guest_message_mentions_arrival(text) and not _LATE_INQUIRY.search(text):
        return None
    if parse_guest_stated_arrival(text, reservation, reference_at=reference_at) is not None:
        return "time_stated"
    if _LATE_INQUIRY.search(text) or guest_message_mentions_arrival(text):
        return "late_inquiry"
    return None


def save_stated_arrival(
    reservation: Reservation,
    *,
    text: str,
    reference_at: datetime | None = None,
) -> datetime | None:
    parsed = parse_guest_stated_arrival(text, reservation, reference_at=reference_at)
    reservation.guest_stated_arrival_text = (text or "")[:255]
    reservation.guest_stated_arrival_at = parsed
    reservation.save(
        update_fields=[
            "guest_stated_arrival_text",
            "guest_stated_arrival_at",
            "updated_at",
        ]
    )
    return parsed


def _dedup_hint(kind: ArrivalInboundKind) -> str:
    return f"{HINT_ARRIVAL_AUTO_REPLY}:{kind}"


def _auto_reply_sent_today(reservation: Reservation, kind: ArrivalInboundKind) -> bool:
    now = property_local_now(reservation.property)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hint = _dedup_hint(kind)
    return GuestMessageDraft.objects.filter(
        reservation=reservation,
        hint=hint,
        sent_at__gte=start_of_day,
    ).exists()


def _format_stated_time(reservation: Reservation, parsed: datetime | None, text: str) -> str:
    if (text or "").strip():
        return text.strip()[:120]
    if parsed is not None:
        tz = parsed.tzinfo
        local = parsed.astimezone(tz) if tz else parsed
        return local.strftime("%H:%M")
    return ""


def build_arrival_auto_reply(
    reservation: Reservation,
    kind: ArrivalInboundKind,
    *,
    parsed: datetime | None = None,
    raw_text: str = "",
) -> str:
    if kind == "late_inquiry":
        return render_arrival_late_inquiry_message(reservation, message_text=raw_text)
    stated = _format_stated_time(reservation, parsed, raw_text)
    return render_arrival_time_saved_message(
        reservation,
        stated_time=stated,
        parsed_late=is_late_arrival(reservation, parsed),
        message_text=raw_text,
    )


def _save_time_for_kind(
    reservation: Reservation,
    body: str,
    kind: ArrivalInboundKind,
    *,
    stated_time_raw: str = "",
    reference_at: datetime | None = None,
) -> datetime | None:
    if kind != "time_stated":
        return None
    save_text = (body or "").strip() or (stated_time_raw or "").strip()
    if not save_text:
        return None
    parsed = save_stated_arrival(reservation, text=save_text, reference_at=reference_at)
    if parsed is None and stated_time_raw and stated_time_raw != save_text:
        return save_stated_arrival(
            reservation,
            text=stated_time_raw,
            reference_at=reference_at,
        )
    return parsed


def send_arrival_auto_reply(
    reservation: Reservation,
    *,
    channel: str,
    body: str,
    kind: ArrivalInboundKind,
    language: str | None = None,
    used_llm: bool = False,
) -> dict:
    draft_channel = _CHANNEL_MAP.get(channel)
    if draft_channel is None:
        return {"status": "skipped", "reason": "unsupported_channel"}

    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.REACTIVE,
        reply_language=language,
        message_text=body,
    )
    lang = ctx.language

    audit = arrival_llm_audit_fields() if used_llm else {"llm_model": "", "prompt_version": ""}
    draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.REPLY,
        hint=_dedup_hint(kind),
        llm_body_text=body,
        final_body_text=body,
        language=lang[:8],
        language_source=ctx.source.value,
        language_reason=(ctx.reason or "")[:255],
        channel=draft_channel,
        llm_model=audit["llm_model"],
        prompt_version=audit["prompt_version"],
    )
    try:
        send_guest_message(
            reservation=reservation,
            draft=draft,
            channel=draft_channel,
            body_text=body,
            api_application=None,
        )
    except ValueError as exc:
        logger.warning(
            "arrival auto-reply send failed reservation_id=%s channel=%s: %s",
            reservation.pk,
            channel,
            exc,
        )
        return {"status": "send_failed", "detail": str(exc)}

    draft.sent_at = timezone.now()
    draft.save(update_fields=["sent_at"])
    return {"status": "sent", "kind": kind, "channel": channel, "used_llm": used_llm}


def _finalize_arrival_handling(
    reservation: Reservation,
    body: str,
    *,
    channel: str,
    kind: ArrivalInboundKind,
    parsed: datetime | None,
    reply_body: str | None,
    reply_language: str | None = None,
    used_llm: bool = False,
) -> dict:
    prop = reservation.property
    reply_result: dict | None = None
    if (
        reply_body
        and prop.guest_arrival_auto_reply_enabled
        and not _auto_reply_sent_today(reservation, kind)
    ):
        reply_result = send_arrival_auto_reply(
            reservation,
            channel=channel,
            body=reply_body,
            kind=kind,
            language=reply_language,
            used_llm=used_llm,
        )

    return {
        "status": "guest_arrival_handled",
        "kind": kind,
        "parsed_at": parsed.isoformat() if parsed else None,
        "reply": reply_result,
        "used_llm": used_llm,
    }


def _handle_arrival_fallback(
    reservation: Reservation,
    body: str,
    *,
    channel: str,
    reference_at: datetime | None = None,
) -> dict | None:
    kind = classify_inbound(body, reservation, reference_at=reference_at)
    if kind is None:
        return None

    parsed = _save_time_for_kind(
        reservation,
        body,
        kind,
        reference_at=reference_at,
    )
    reply_body = None
    if reservation.property.guest_arrival_auto_reply_enabled and not _auto_reply_sent_today(
        reservation, kind
    ):
        reply_body = build_arrival_auto_reply(
            reservation,
            kind,
            parsed=parsed,
            raw_text=body,
        )

    return _finalize_arrival_handling(
        reservation,
        body,
        channel=channel,
        kind=kind,
        parsed=parsed,
        reply_body=reply_body,
        used_llm=False,
    )


def _handle_arrival_llm(
    reservation: Reservation,
    body: str,
    *,
    channel: str,
    llm_result: ArrivalLlmResult,
    reference_at: datetime | None = None,
) -> dict:
    kind = llm_result.scenario
    if kind is None:
        raise GuestComposeError("LLM result missing scenario")

    parsed = _save_time_for_kind(
        reservation,
        body,
        kind,
        stated_time_raw=llm_result.stated_time_raw,
        reference_at=reference_at,
    )
    reply_body = llm_result.reply_text if llm_result.reply_text else None

    return _finalize_arrival_handling(
        reservation,
        body,
        channel=channel,
        kind=kind,
        parsed=parsed,
        reply_body=reply_body,
        reply_language=llm_result.reply_language,
        used_llm=True,
    )


def maybe_handle_guest_arrival_inbound(
    reservation: Reservation,
    body: str,
    *,
    channel: str,
    reference_at: datetime | None = None,
) -> dict | None:
    """Parse arrival info, save to reservation, auto-reply on same channel. Returns None if N/A."""
    if reservation.status != Reservation.Status.EXPECTED:
        return None

    if llm_configured():
        try:
            llm_result = analyze_and_compose_arrival_reply(
                reservation,
                body,
                channel=channel,
            )
            if not llm_result.is_arrival_related or llm_result.scenario is None:
                return None
            return _handle_arrival_llm(
                reservation,
                body,
                channel=channel,
                llm_result=llm_result,
                reference_at=reference_at,
            )
        except GuestComposeError as exc:
            logger.warning(
                "arrival LLM failed, using regex fallback reservation_id=%s: %s",
                reservation.pk,
                exc,
            )

    return _handle_arrival_fallback(
        reservation,
        body,
        channel=channel,
        reference_at=reference_at,
    )
