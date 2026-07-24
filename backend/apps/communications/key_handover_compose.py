"""Render self-service key handover guide from structured guest_info.guide sections."""

from __future__ import annotations

from string import Formatter

from apps.communications.guest_arrival_policy import after_hours_contact_phone
from apps.communications.guest_compose import build_compose_context, render_guest_template
from apps.communications.guest_compose_defaults import DEFAULT_GUEST_NAME
from apps.communications.guest_language_context import LanguageMode
from apps.properties.guest_info import (
    breakfast_hours_from_guest_info,
    effective_unit_key_label,
    guide_from_guest_info,
)
from apps.reservations.models import Reservation


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _format_template(template: str, context: dict[str, str]) -> str:
    if not template:
        return ""
    try:
        return Formatter().vformat(template, (), _SafeFormatDict(context))
    except ValueError:
        return template


def _text_for_lang(texts: dict[str, str], lang: str) -> str:
    base = (lang or "en").split("-")[0].lower()
    if base in texts and texts[base]:
        return texts[base]
    if texts.get("en"):
        return texts["en"]
    for value in texts.values():
        if value:
            return value
    return ""


def reservation_key_handover_labels(reservation: Reservation) -> tuple[str, str]:
    """Return (key_label, room_code) from the first reservation unit."""
    unit_row = (
        reservation.units.select_related("unit")
        .order_by("sort_order", "id")
        .first()
    )
    if unit_row and unit_row.unit_id:
        unit = unit_row.unit
        room_code = (unit.code or unit_row.room_name or "").strip()
        key_label = effective_unit_key_label(unit) or room_code
        return key_label, room_code
    room_name = (unit_row.room_name if unit_row else "").strip()
    return room_name, room_name


def build_key_handover_compose_context(reservation: Reservation) -> dict:
    context = build_compose_context(reservation, mode=LanguageMode.PROACTIVE)
    raw_name = (reservation.booker_name or "").strip()
    lang = context["language"]
    first_name = (
        raw_name.split()[0]
        if raw_name
        else _text_for_lang(DEFAULT_GUEST_NAME, lang)
    )
    key_label, room_code = reservation_key_handover_labels(reservation)
    breakfast_hours = breakfast_hours_from_guest_info(
        reservation.property.guest_info,
        lang,
    ) or "7:30–9:30"
    contact_phone = after_hours_contact_phone(reservation.property) or context.get(
        "contact_phone", ""
    )

    return {
        **context,
        "first_name": first_name,
        "key_label": key_label,
        "room_code": room_code,
        "breakfast_hours": breakfast_hours,
        "contact_phone": contact_phone,
    }


def _placeholder_context(compose_context: dict) -> dict[str, str]:
    return {
        "first_name": str(compose_context.get("first_name") or ""),
        "room_code": str(compose_context.get("room_code") or ""),
        "key_label": str(compose_context.get("key_label") or ""),
        "check_in_time": str(compose_context.get("check_in_time") or ""),
        "breakfast_hours": str(compose_context.get("breakfast_hours") or ""),
        "contact_phone": str(compose_context.get("contact_phone") or ""),
        "maps_link": str(compose_context.get("maps_link") or ""),
        "address": str(compose_context.get("address") or ""),
    }


def render_key_handover_guide(reservation: Reservation) -> str:
    """Assemble the key pickup guide from guest_info.guide sections."""
    guide = guide_from_guest_info(reservation.property.guest_info)
    sections = guide.get("sections") or {}
    if not sections:
        return ""

    compose_context = build_key_handover_compose_context(reservation)
    lang_ctx = compose_context["language_context"]
    order = guide.get("order") or list(sections.keys())
    enabled = guide.get("enabled") or {}
    fmt = _placeholder_context(compose_context)

    lines: list[str] = []
    for section_key in order:
        if not enabled.get(section_key, True):
            continue
        block = sections.get(section_key)
        if not isinstance(block, dict):
            continue

        def render_fn(lang: str, block=block) -> str:
            text = _text_for_lang(block, lang)
            return _format_template(text, fmt).strip()

        section_text = render_guest_template(reservation, render_fn, lang_ctx)
        if section_text:
            if lines:
                lines.append("")
            lines.append(section_text)

    return "\n".join(lines)


def resolve_guide_steps(reservation: Reservation) -> list[dict]:
    """Return configured key-guide image steps from guest_info.guide."""
    guide = guide_from_guest_info(reservation.property.guest_info)
    steps = guide.get("steps")
    return steps if isinstance(steps, list) else []
