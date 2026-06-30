"""LLM analysis and reply composition for guest parking questions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from apps.ai.provider import GuestComposeError, complete_chat_json, llm_model, prompt_version
from apps.communications.guest_language_context import LanguageMode
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.communications.guest_parking_patterns import classify_parking_only
from apps.properties.guest_info import build_guest_facts_for_llm, render_parking_reply_text
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)

FOOTER = "Managed by stay.hr — https://stay.hr/"


@dataclass(frozen=True)
class ParkingLlmResult:
    is_parking_related: bool
    reply_language: str
    reply_text: str


def build_parking_llm_context(
    reservation: Reservation,
    body: str,
    *,
    channel: str,
) -> dict:
    prop = reservation.property
    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.REACTIVE,
        message_text=body,
    )
    lang = ctx.language
    return {
        "guest_message": (body or "").strip(),
        "channel": channel,
        "reservation": {
            "status": reservation.status,
            "check_in_date": reservation.check_in.isoformat(),
            "guest_name": reservation.booker_name or "",
            "booking_code": reservation.booking_code or reservation.external_id or "",
            "notes": (reservation.notes or "").strip(),
        },
        "guest_facts": build_guest_facts_for_llm(prop, lang),
    }


def _system_prompt() -> str:
    return (
        "You are a professional hotel reception assistant. "
        "Analyze the guest message and decide if it is ONLY about parking "
        "(not arrival time or check-in). "
        "If yes, write a short reply using ONLY facts from guest_facts.parking in the JSON context. "
        "Never invent prices, zones, or policies not present in the context. "
        "Reply in the same language as the guest message (set reply_language to ISO 639-1 code). "
        "Keep a warm, concise reception tone. "
        f"End with the property name and this footer on its own line: {FOOTER}\n\n"
        "Return JSON only with keys:\n"
        "- is_parking_related (boolean)\n"
        "- reply_language (ISO 639-1)\n"
        "- reply_text (empty string if not parking-related)"
    )


def _user_prompt(context: dict) -> str:
    return (
        "Analyze the guest message and compose a parking reply if it is a parking-only question.\n"
        f"Data (JSON):\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def _parse_llm_response(
    reservation: Reservation,
    body: str,
    raw: dict,
) -> ParkingLlmResult:
    is_parking = bool(raw.get("is_parking_related"))
    reply_text = (raw.get("reply_text") or "").strip()
    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.REACTIVE,
        reply_language=str(raw.get("reply_language") or ""),
        message_text=body,
    )
    reply_language = ctx.language

    if is_parking and not reply_text:
        raise GuestComposeError("LLM marked parking-related but returned empty reply_text")

    return ParkingLlmResult(
        is_parking_related=is_parking,
        reply_language=reply_language,
        reply_text=reply_text,
    )


def analyze_and_compose_parking_reply(
    reservation: Reservation,
    body: str,
    *,
    channel: str,
) -> ParkingLlmResult:
    context = build_parking_llm_context(reservation, body, channel=channel)
    raw = complete_chat_json(_system_prompt(), _user_prompt(context))
    result = _parse_llm_response(reservation, body, raw)
    logger.info(
        "parking LLM analyzed reservation_id=%s related=%s lang=%s model=%s",
        reservation.pk,
        result.is_parking_related,
        result.reply_language,
        llm_model(),
    )
    return result


def parking_llm_audit_fields() -> dict[str, str]:
    return {"llm_model": llm_model(), "prompt_version": prompt_version()}


def build_parking_auto_reply(
    reservation: Reservation,
    body: str,
    *,
    language: str | None = None,
) -> str:
    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.REACTIVE,
        reply_language=language,
        message_text=body,
    )
    lang = ctx.language
    return render_parking_reply_text(
        reservation.property,
        lang,
        variant="standard",
        reservation_notes=reservation.notes or "",
    )


def is_parking_only_message(text: str) -> bool:
    return classify_parking_only(text)
