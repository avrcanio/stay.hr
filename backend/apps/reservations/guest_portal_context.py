"""Frozen guest portal context — sections + localized content (no ORM in UI)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from django.conf import settings

from apps.communications.guest_arrival_policy import after_hours_contact_phone
from apps.communications.guest_language_constants import normalize_iso639_1
from apps.communications.guest_language_context import LanguageMode
from apps.communications.guest_language_resolver import GuestLanguageResolver
from apps.communications.guest_message_send import build_wa_me_url
from apps.communications.key_handover_compose import (
    reservation_key_handover_labels,
)
from apps.integrations.whatsapp.phone import normalize_phone
from apps.properties.guest_info import (
    format_wifi_block,
    guest_maps_url,
    guest_text,
    guide_from_guest_info,
    normalize_guest_info,
    property_entrance_image_path,
    property_entrance_image_rel,
    render_parking_reply_text,
    wifi_facts_from_guest_info,
)
from apps.properties.self_service import is_self_service_active
from apps.reservations.models import GuestPortalAccess, Reservation

PORTAL_SECTION_ORDER = (
    "welcome",
    "arrival",
    "key_guide",
    "parking",
    "wifi",
    "breakfast",
    "contact",
)

_ALLOWED_GUIDE_IMAGE_PREFIXES = (
    "assets/guest-portal/",
    "assets/whatsapp/",
)


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


@dataclass(frozen=True)
class GuestPortalContext:
    reservation_id: int
    property_name: str
    language: str
    sections: tuple[str, ...]
    content: Mapping[str, Any]
    branding: Mapping[str, Any]
    self_service_active: bool = False


def _resolve_language(reservation: Reservation, *, language: str | None) -> str:
    override = normalize_iso639_1(language) if language else None
    if override:
        return override
    ctx = GuestLanguageResolver.resolve(
        reservation,
        mode=LanguageMode.PROACTIVE,
    )
    return normalize_iso639_1(ctx.language) or "en"


def _contact_phone(property) -> str:
    direct = after_hours_contact_phone(property)
    if direct:
        return direct
    contact = property.contact if isinstance(property.contact, dict) else {}
    for key in ("phone", "mobile", "reception_phone", "whatsapp"):
        val = str(contact.get(key) or "").strip()
        if val:
            return val
    return ""


def _whatsapp_url(property, phone: str) -> str:
    contact = property.contact if isinstance(property.contact, dict) else {}
    wa_raw = str(contact.get("whatsapp") or contact.get("phone") or phone or "").strip()
    digits = normalize_phone(wa_raw)
    if not digits:
        return ""
    return build_wa_me_url(digits, "")


def _welcome_message(property, lang: str, *, guest_name: str) -> str:
    name = (guest_name or "").strip() or "guest"
    templates = {
        "hr": f"Dobrodošli{', ' + name if name != 'guest' else ''}! Ovdje su informacije za vaš boravak u {property.name}.",
        "en": f"Welcome{', ' + name if name != 'guest' else ''}! Here is the information for your stay at {property.name}.",
        "de": f"Willkommen{', ' + name if name != 'guest' else ''}! Hier finden Sie Infos zu Ihrem Aufenthalt in {property.name}.",
        "es": f"¡Bienvenido{', ' + name if name != 'guest' else ''}! Aquí tiene la información de su estancia en {property.name}.",
        "fr": f"Bienvenue{', ' + name if name != 'guest' else ''} ! Voici les informations pour votre séjour à {property.name}.",
        "sk": f"Vitajte{', ' + name if name != 'guest' else ''}! Tu sú informácie k vášmu pobytu v {property.name}.",
        "it": f"Benvenuti{', ' + name if name != 'guest' else ''}! Ecco le informazioni per il vostro soggiorno a {property.name}.",
    }
    base = (lang or "en").split("-")[0].lower()
    return templates.get(base) or templates["en"]


def _breakfast_payload(property, lang: str) -> dict[str, str] | None:
    info = normalize_guest_info(property.guest_info)
    facts = info.get("facts") or {}
    raw_breakfast = facts.get("breakfast")
    text = ""
    breakfast_hours = ""
    if isinstance(raw_breakfast, dict):
        localized = {
            k: str(v).strip()
            for k, v in raw_breakfast.items()
            if k != "hours" and str(v or "").strip()
        }
        text = _text_for_lang(localized, lang)
        breakfast_hours = str(raw_breakfast.get("hours") or "").strip()
    if not text:
        text = guest_text(property, "breakfast", lang)
    if not text:
        return None
    payload: dict[str, str] = {"text": text}
    if breakfast_hours:
        payload["hours"] = breakfast_hours
    return payload


def _arrival_payload(property, lang: str, *, token: str) -> dict[str, str] | None:
    text = guest_text(property, "entrance", lang)
    maps_url = guest_maps_url(property)
    image_url = ""
    try:
        path = property_entrance_image_path(property)
        if path.is_file():
            # Bust browser/CDN cache when the asset is replaced (orientation fixes, etc.).
            version = int(path.stat().st_mtime)
            image_url = f"/api/g/{token}/entrance?v={version}"
    except OSError:
        image_url = ""
    if not text and not maps_url and not image_url:
        return None
    payload: dict[str, str] = {}
    if text:
        payload["text"] = text
    if maps_url:
        payload["maps_url"] = maps_url
    if image_url:
        payload["image_url"] = image_url
        payload["image_rel"] = property_entrance_image_rel(property)
    return payload or None


def _wifi_payload(property, lang: str) -> dict[str, str] | None:
    ssid, password = wifi_facts_from_guest_info(property.guest_info)
    block = format_wifi_block(property, lang)
    if not ssid and not block:
        return None
    payload: dict[str, str] = {}
    if ssid:
        payload["ssid"] = ssid
    if password:
        payload["password"] = password
    if block:
        payload["text"] = block
    return payload


def _format_caption(template: str, *, key_label: str, room_code: str) -> str:
    if not template:
        return ""
    try:
        return template.format(key_label=key_label or "{key_label}", room_code=room_code or "{room_code}")
    except (KeyError, ValueError):
        return template


def _key_guide_payload(
    property,
    lang: str,
    *,
    token: str,
    reservation: Reservation,
) -> dict[str, Any] | None:
    if not is_self_service_active(property, reservation.check_in):
        return None
    guide = guide_from_guest_info(property.guest_info)
    steps_raw = guide.get("steps") or []
    if not isinstance(steps_raw, list) or not steps_raw:
        return None

    key_label, room_code = reservation_key_handover_labels(reservation)
    steps: list[dict[str, str]] = []
    for index, step in enumerate(steps_raw):
        if not isinstance(step, dict):
            continue
        caption_block = step.get("caption") if isinstance(step.get("caption"), dict) else {}
        caption = _text_for_lang(caption_block, lang)
        caption = _format_caption(caption, key_label=key_label, room_code=room_code)
        image_rel = str(step.get("image") or "").strip()
        image_url = ""
        if image_rel and guide_step_image_path(image_rel) is not None:
            path = guide_step_image_path(image_rel)
            try:
                version = int(path.stat().st_mtime) if path is not None else 0
            except OSError:
                version = 0
            image_url = f"/api/g/{token}/steps/{index}?v={version}"
        if not caption and not image_url:
            continue
        item: dict[str, str] = {"index": str(index)}
        if caption:
            item["caption"] = caption
        if image_url:
            item["image_url"] = image_url
            item["image_rel"] = image_rel
        steps.append(item)

    if not steps:
        return None
    payload: dict[str, Any] = {"steps": steps}
    if room_code:
        payload["room_code"] = room_code
    if key_label:
        payload["key_label"] = key_label
    return payload


def guide_step_image_path(rel: str) -> Path | None:
    """Resolve a guide step image under BASE_DIR; reject path traversal."""
    cleaned = (rel or "").strip().lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        return None
    if not cleaned.startswith(_ALLOWED_GUIDE_IMAGE_PREFIXES):
        return None
    path = Path(settings.BASE_DIR) / cleaned
    try:
        path.resolve().relative_to(Path(settings.BASE_DIR).resolve())
    except ValueError:
        return None
    if path.is_file():
        return path
    return None


def build_guest_portal_context(
    access: GuestPortalAccess,
    *,
    language: str | None = None,
) -> GuestPortalContext:
    reservation = access.reservation
    prop = reservation.property
    lang = _resolve_language(reservation, language=language)
    self_service_active = is_self_service_active(prop, reservation.check_in)

    content: dict[str, Any] = {}
    sections: list[str] = []

    guest_name = (reservation.booker_name or "").strip()
    welcome = {
        "property_name": prop.name,
        "guest_name": guest_name,
        "check_in": reservation.check_in.isoformat(),
        "check_out": reservation.check_out.isoformat(),
        "message": _welcome_message(prop, lang, guest_name=guest_name),
    }
    content["welcome"] = welcome
    sections.append("welcome")

    arrival = _arrival_payload(prop, lang, token=str(access.token))
    if arrival:
        content["arrival"] = arrival
        sections.append("arrival")

    key_guide = _key_guide_payload(
        prop,
        lang,
        token=str(access.token),
        reservation=reservation,
    )
    if key_guide:
        content["key_guide"] = key_guide
        sections.append("key_guide")

    parking_text = render_parking_reply_text(
        prop,
        lang,
        variant="post_checkin",
        reservation_notes=getattr(reservation, "notes", "") or "",
    )
    if parking_text:
        content["parking"] = {"text": parking_text}
        sections.append("parking")

    wifi = _wifi_payload(prop, lang)
    if wifi:
        content["wifi"] = wifi
        sections.append("wifi")

    breakfast = _breakfast_payload(prop, lang)
    if breakfast:
        content["breakfast"] = breakfast
        sections.append("breakfast")

    phone = _contact_phone(prop)
    wa_url = _whatsapp_url(prop, phone)
    if phone or wa_url:
        contact: dict[str, str] = {}
        if phone:
            contact["phone"] = phone
        if wa_url:
            contact["whatsapp_url"] = wa_url
        content["contact"] = contact
        sections.append("contact")

    # Preserve declared order; only include sections that have content.
    ordered = tuple(s for s in PORTAL_SECTION_ORDER if s in sections)

    branding = prop.branding if isinstance(prop.branding, dict) else {}

    return GuestPortalContext(
        reservation_id=reservation.pk,
        property_name=prop.name,
        language=lang,
        sections=ordered,
        content=content,
        branding=branding,
        self_service_active=self_service_active,
    )


def serialize_guest_portal_context(ctx: GuestPortalContext) -> dict[str, Any]:
    return {
        "reservation_id": ctx.reservation_id,
        "property_name": ctx.property_name,
        "language": ctx.language,
        "sections": list(ctx.sections),
        "content": dict(ctx.content),
        "branding": dict(ctx.branding),
        "self_service_active": ctx.self_service_active,
    }


def entrance_image_file_for_access(access: GuestPortalAccess) -> Path | None:
    """Return absolute path to entrance image if configured and present on disk."""
    prop = access.reservation.property
    path = property_entrance_image_path(prop)
    if path.is_file():
        return path
    # Fall back to default asset under BASE_DIR when rel is empty / missing.
    fallback = Path(settings.BASE_DIR) / "assets" / "whatsapp" / "uzorita_entrance.jpg"
    if fallback.is_file():
        return fallback
    return None


def key_guide_step_file_for_access(access: GuestPortalAccess, index: int) -> Path | None:
    """Return absolute path for guide step image ``index`` when portal is self-service active."""
    reservation = access.reservation
    prop = reservation.property
    if not is_self_service_active(prop, reservation.check_in):
        return None
    guide = guide_from_guest_info(prop.guest_info)
    steps = guide.get("steps") or []
    if not isinstance(steps, list) or index < 0 or index >= len(steps):
        return None
    step = steps[index]
    if not isinstance(step, dict):
        return None
    return guide_step_image_path(str(step.get("image") or ""))
