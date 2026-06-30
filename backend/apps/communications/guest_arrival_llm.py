"""LLM analysis and reply composition for guest arrival-time messages."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from apps.ai.provider import GuestComposeError, complete_chat_json, llm_model, prompt_version
from apps.communications.guest_arrival_policy import (
    after_hours_contact_phone,
    evaluate_arrival_time,
    format_time_hm,
)
from apps.communications.guest_language_context import LanguageMode
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.integrations.whatsapp.arrival_time_parse import parse_guest_stated_arrival
from apps.properties.guest_info import build_guest_facts_for_llm
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)

ArrivalScenario = Literal["time_stated", "late_inquiry"]

FOOTER = "Managed by stay.hr — https://stay.hr/"


@dataclass(frozen=True)
class ArrivalLlmResult:
    is_arrival_related: bool
    scenario: ArrivalScenario | None
    reply_language: str
    reply_text: str
    stated_time_raw: str


def build_arrival_llm_context(
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
    parsed = parse_guest_stated_arrival(body, reservation)
    window_status = evaluate_arrival_time(reservation, parsed) if parsed else None

    stated_at = reservation.guest_stated_arrival_at
    return {
        "guest_message": (body or "").strip(),
        "channel": channel,
        "reservation": {
            "status": reservation.status,
            "check_in_date": reservation.check_in.isoformat(),
            "guest_name": reservation.booker_name or "",
            "booking_code": reservation.booking_code or reservation.external_id or "",
            "guest_stated_arrival_text": reservation.guest_stated_arrival_text or "",
            "guest_stated_arrival_at": stated_at.isoformat() if stated_at else None,
        },
        "arrival_policy": {
            "property_name": prop.name,
            "check_in_from": format_time_hm(prop.check_in_time),
            "check_in_latest": format_time_hm(prop.check_in_latest_time) or None,
            "after_hours_policy": prop.after_hours_arrival_policy,
            "after_hours_contact_phone": after_hours_contact_phone(prop) or None,
            "window_status_if_parsed": window_status,
        },
        "guest_facts": build_guest_facts_for_llm(prop, lang),
    }


def _system_prompt() -> str:
    return (
        "You are a professional hotel reception assistant. "
        "Analyze the guest message and decide if it is about arrival time or late check-in. "
        "If yes, write a short reply using ONLY facts from the JSON context. "
        "Never invent prices, policies, phone numbers, or times not present in arrival_policy or guest_facts. "
        "Reply in the same language as the guest message (set reply_language to ISO 639-1 code). "
        "Keep a warm, concise reception tone. "
        f"End with the property name and this footer on its own line: {FOOTER}\n\n"
        "Return JSON only with keys:\n"
        "- is_arrival_related (boolean)\n"
        "- scenario: null | \"time_stated\" | \"late_inquiry\"\n"
        "- reply_language (ISO 639-1, e.g. hr, en, de)\n"
        "- reply_text (empty string if not arrival-related)\n"
        "- stated_time_raw (guest's time phrase if any, else empty string)\n\n"
        "Scenarios:\n"
        "- late_inquiry: guest asks about late arrival without a concrete time — explain check-in window, "
        "mention entrance/parking from guest_facts if relevant, ask for exact arrival time.\n"
        "- time_stated + within window: thank guest and confirm the time was recorded.\n"
        "- time_stated + late + after_hours_policy contact: thank, note time, give after_hours_contact_phone.\n"
        "- time_stated + late + after_hours_policy not_allowed: explain entry after check_in_latest is not possible."
    )


def _user_prompt(context: dict) -> str:
    return (
        "Analyze the guest message and compose a reply if it is about arrival time.\n"
        f"Data (JSON):\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def _parse_llm_response(
    reservation: Reservation,
    body: str,
    raw: dict,
) -> ArrivalLlmResult:
    is_arrival = bool(raw.get("is_arrival_related"))
    scenario_raw = (raw.get("scenario") or "").strip().lower()
    scenario: ArrivalScenario | None = None
    if scenario_raw in ("time_stated", "late_inquiry"):
        scenario = scenario_raw  # type: ignore[assignment]

    reply_text = (raw.get("reply_text") or "").strip()
    stated_time_raw = (raw.get("stated_time_raw") or "").strip()
    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.REACTIVE,
        reply_language=str(raw.get("reply_language") or ""),
        message_text=body,
    )
    reply_language = ctx.language

    if is_arrival and scenario is None:
        scenario = "late_inquiry" if not stated_time_raw else "time_stated"

    if is_arrival and not reply_text:
        raise GuestComposeError("LLM marked arrival-related but returned empty reply_text")

    return ArrivalLlmResult(
        is_arrival_related=is_arrival,
        scenario=scenario if is_arrival else None,
        reply_language=reply_language,
        reply_text=reply_text,
        stated_time_raw=stated_time_raw,
    )


def analyze_and_compose_arrival_reply(
    reservation: Reservation,
    body: str,
    *,
    channel: str,
) -> ArrivalLlmResult:
    """Single LLM call: classify arrival intent and compose reply."""
    context = build_arrival_llm_context(reservation, body, channel=channel)
    raw = complete_chat_json(_system_prompt(), _user_prompt(context))
    result = _parse_llm_response(reservation, body, raw)
    logger.info(
        "arrival LLM analyzed reservation_id=%s related=%s scenario=%s lang=%s model=%s",
        reservation.pk,
        result.is_arrival_related,
        result.scenario,
        result.reply_language,
        llm_model(),
    )
    return result


def arrival_llm_audit_fields() -> dict[str, str]:
    return {"llm_model": llm_model(), "prompt_version": prompt_version()}
