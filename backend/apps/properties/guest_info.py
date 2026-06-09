"""Property.guest_info schema, normalization, and text resolution for guest messages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from django.conf import settings

from apps.communications.guest_compose_defaults import (
    DEFAULT_ENTRANCE_IMAGE,
    DEFAULT_TEXTS,
    MAPS_LINK,
)
from apps.communications.guest_compose_language import SUPPORTED_COMPOSE_LANGS
from apps.properties.models import Property

GUEST_INFO_TEXT_KEYS = frozenset(DEFAULT_TEXTS.keys())

LOCALIZED_FACT_KEYS = frozenset(
    {
        "key_handover",
        "late_arrival",
        "breakfast",
        "tourist_tax",
    }
)

WIFI_LABELS: dict[str, dict[str, str]] = {
    "hr": {"ssid": "WiFi", "password": "Lozinka"},
    "en": {"ssid": "WiFi", "password": "Password"},
    "de": {"ssid": "WLAN", "password": "Passwort"},
    "es": {"ssid": "WiFi", "password": "Contraseña"},
    "fr": {"ssid": "WiFi", "password": "Mot de passe"},
    "sk": {"ssid": "WiFi", "password": "Heslo"},
}


class LocalizedText(TypedDict, total=False):
    hr: str
    en: str
    de: str
    es: str
    fr: str
    sk: str


class GuestInfoWifi(TypedDict, total=False):
    ssid: str
    password: str
    instructions: LocalizedText


def _normalize_localized(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {
        lang: str(raw.get(lang) or "").strip()
        for lang in SUPPORTED_COMPOSE_LANGS
        if str(raw.get(lang) or "").strip()
    }


def _normalize_wifi(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    instructions = _normalize_localized(raw.get("instructions"))
    wifi: dict[str, Any] = {}
    ssid = str(raw.get("ssid") or "").strip()
    password = str(raw.get("password") or "").strip()
    if ssid:
        wifi["ssid"] = ssid
    if password:
        wifi["password"] = password
    if instructions:
        wifi["instructions"] = instructions
    return wifi


def normalize_guest_info(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    links = data.get("links") if isinstance(data.get("links"), dict) else {}
    assets = data.get("assets") if isinstance(data.get("assets"), dict) else {}
    facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    texts = data.get("texts") if isinstance(data.get("texts"), dict) else {}

    normalized_texts: dict[str, dict[str, str]] = {}
    for key in GUEST_INFO_TEXT_KEYS:
        block = texts.get(key)
        if isinstance(block, dict):
            localized = _normalize_localized(block)
            if localized:
                normalized_texts[key] = localized

    normalized_facts: dict[str, Any] = {
        "ai_notes": str(facts.get("ai_notes") or "").strip(),
        "reception_hours": str(facts.get("reception_hours") or "").strip(),
        "wifi": _normalize_wifi(facts.get("wifi")),
    }
    for fact_key in LOCALIZED_FACT_KEYS:
        localized = _normalize_localized(facts.get(fact_key))
        if localized:
            normalized_facts[fact_key] = localized

    return {
        "links": {
            "maps_url": str(links.get("maps_url") or "").strip(),
        },
        "assets": {
            "entrance_image": str(assets.get("entrance_image") or "").strip(),
        },
        "facts": normalized_facts,
        "texts": normalized_texts,
    }


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


def guest_text(
    property: Property,
    key: str,
    lang: str,
    **fmt: Any,
) -> str:
    info = normalize_guest_info(property.guest_info)
    property_block = (info.get("texts") or {}).get(key)
    if isinstance(property_block, dict) and property_block:
        template = _text_for_lang(property_block, lang)
    else:
        fallback = DEFAULT_TEXTS.get(key)
        if not fallback:
            return ""
        template = _text_for_lang(fallback, lang)
    if fmt:
        return template.format(**fmt)
    return template


def wifi_facts_from_guest_info(raw: Any) -> tuple[str, str]:
    """Return (ssid, password) from guest_info JSON."""
    info = normalize_guest_info(raw)
    wifi = (info.get("facts") or {}).get("wifi") or {}
    if not isinstance(wifi, dict):
        return "", ""
    return str(wifi.get("ssid") or "").strip(), str(wifi.get("password") or "").strip()


def merge_wifi_into_guest_info(raw: Any, *, ssid: str, password: str) -> dict[str, Any]:
    """Update facts.wifi in guest_info; preserves other keys."""
    info = normalize_guest_info(raw)
    facts = dict(info.get("facts") or {})
    wifi: dict[str, Any] = {}
    ssid_clean = (ssid or "").strip()
    password_clean = (password or "").strip()
    if ssid_clean:
        wifi["ssid"] = ssid_clean
    if password_clean:
        wifi["password"] = password_clean
    facts["wifi"] = wifi
    info["facts"] = facts
    return normalize_guest_info(info)


def format_wifi_block(property: Property, lang: str) -> str:
    """Localized WiFi lines for guest messages (empty if no SSID configured)."""
    info = normalize_guest_info(property.guest_info)
    wifi = (info.get("facts") or {}).get("wifi") or {}
    if not isinstance(wifi, dict):
        return ""
    ssid = str(wifi.get("ssid") or "").strip()
    if not ssid:
        return ""
    password = str(wifi.get("password") or "").strip()
    base = (lang or "en").split("-")[0].lower()
    labels = WIFI_LABELS.get(base) or WIFI_LABELS["en"]
    lines: list[str] = []
    instructions = wifi.get("instructions")
    if isinstance(instructions, dict):
        intro = _text_for_lang(instructions, lang)
        if intro:
            lines.append(intro)
    lines.append(f"{labels['ssid']}: {ssid}")
    if password:
        lines.append(f"{labels['password']}: {password}")
    return "\n".join(lines)


def guest_maps_url(property: Property) -> str:
    info = normalize_guest_info(property.guest_info)
    url = (info.get("links") or {}).get("maps_url") or ""
    return url or MAPS_LINK


def property_entrance_image_rel(property: Property) -> str:
    info = normalize_guest_info(property.guest_info)
    rel = (info.get("assets") or {}).get("entrance_image") or ""
    return rel or DEFAULT_ENTRANCE_IMAGE


def property_entrance_image_path(property: Property) -> Path:
    rel = property_entrance_image_rel(property)
    return Path(settings.BASE_DIR) / rel


def _localized_fact_text(facts: dict[str, Any], key: str, lang: str) -> str:
    block = facts.get(key)
    if isinstance(block, dict):
        return _text_for_lang(block, lang)
    return ""


def build_guest_facts_for_llm(property: Property, lang: str) -> dict[str, Any]:
    info = normalize_guest_info(property.guest_info)
    facts_section = info.get("facts") or {}
    result: dict[str, Any] = {}

    maps_url = guest_maps_url(property)
    if maps_url:
        result["maps_url"] = maps_url

    ai_notes = str(facts_section.get("ai_notes") or "").strip()
    if ai_notes:
        result["ai_notes"] = ai_notes

    reception_hours = str(facts_section.get("reception_hours") or "").strip()
    if reception_hours:
        result["reception_hours"] = reception_hours

    wifi = facts_section.get("wifi") or {}
    if isinstance(wifi, dict):
        wifi_facts: dict[str, str] = {}
        if wifi.get("ssid"):
            wifi_facts["ssid"] = str(wifi["ssid"])
        if wifi.get("password"):
            wifi_facts["password"] = str(wifi["password"])
        instructions = wifi.get("instructions")
        if isinstance(instructions, dict):
            instr_text = _text_for_lang(instructions, lang)
            if instr_text:
                wifi_facts["instructions"] = instr_text
        if wifi_facts:
            result["wifi"] = wifi_facts

    for fact_key in LOCALIZED_FACT_KEYS:
        text = _localized_fact_text(facts_section, fact_key, lang)
        if text:
            result[fact_key] = text

    for text_key in (
        "entrance",
        "parking",
        "parking_post_checkin",
        "key_handover",
        "late_arrival",
        "breakfast",
        "tourist_tax",
    ):
        if text_key in LOCALIZED_FACT_KEYS:
            continue
        text = guest_text(property, text_key, lang)
        if text:
            result[text_key] = text

    return result
