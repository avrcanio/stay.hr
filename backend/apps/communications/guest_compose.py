"""Guest message compose with deterministic check-in templates and optional LLM."""

from __future__ import annotations

import html
import json
import logging
from decimal import Decimal

from apps.ai.provider import (
    GuestComposeError,
    complete_chat,
    llm_configured,
    llm_model,
    prompt_version,
)
from apps.ai.translate import translate_text, translation_available
from apps.api.language import normalize_app_language
from apps.billing.models import Invoice
from apps.billing.services.payment import resolve_payment_method
from apps.communications.guest_compose_language import (
    SUPPORTED_COMPOSE_LANGS,
    compose_language_for_reservation,
)
from apps.communications.guest_email import _email_context
from apps.communications.guest_message_send import build_message_channels
from apps.communications.models import GuestMessageDraft, GuestMessageIntent
from apps.integrations.models import ChannexMessage, WhatsAppMessage
from apps.reservations.document_intake_sides import MissingIdSide
from apps.reservations.models import Reservation
from apps.tenants.models import ApiApplication

logger = logging.getLogger(__name__)

HINT_CHECKIN_READY = "checkin ready"
HINT_OPERATOR_CHECKIN_COMPLETE = "operator checkin complete"
HINT_AUTOCHECKIN_WHATSAPP_INTRO = "whatsapp autocheckin intro"
HINT_EVISITOR_REGISTERED = "evisitor registered"
HINT_ID_MISSING_SIDES = "id missing sides"
HINT_POST_CHECKIN_AUTO_REPLY = "post_checkin_auto_reply"
HINT_AUTOCHECKIN_WAIVED = "autocheckin waived"
HINT_AUTOCHECKIN_ARRIVAL_THANKS = "autocheckin arrival thanks"

FOOTER = "Managed by stay.hr — https://stay.hr/"

PAYMENT_TEXTS: dict[str, dict[str, str]] = {
    Invoice.PaymentMethod.BOOKING: {
        "hr": "Ukupna cijena: {amount} € — plaćeno u cijelosti putem Booking.com (Payments by Booking.com). Boravak ne plaćate na check-inu.",
        "en": "Total price: €{amount} — paid in full via Booking.com (Payments by Booking.com). No payment due for your stay at check-in.",
        "de": "Gesamtpreis: {amount} € — vollständig über Booking.com (Payments by Booking.com) bezahlt. Keine Zahlung für den Aufenthalt beim Check-in.",
        "es": "Precio total: {amount} € — pagado íntegramente a través de Booking.com (Payments by Booking.com). No hay que pagar la estancia en el check-in.",
        "fr": "Prix total : {amount} € — entièrement réglé via Booking.com (Payments by Booking.com). Aucun paiement du séjour à l’arrivée.",
    },
    Invoice.PaymentMethod.CASH: {
        "hr": "Ukupna cijena: {amount} € — plaćanje gotovinom na check-inu.",
        "en": "Total price: €{amount} — payment in cash at check-in.",
        "de": "Gesamtpreis: {amount} € — Zahlung bar beim Check-in.",
        "es": "Precio total: {amount} € — pago en efectivo en el check-in.",
        "fr": "Prix total : {amount} € — paiement en espèces à l’arrivée.",
    },
    Invoice.PaymentMethod.CARD: {
        "hr": "Ukupna cijena: {amount} € — plaćanje karticom na check-inu.",
        "en": "Total price: €{amount} — payment by card at check-in.",
        "de": "Gesamtpreis: {amount} € — Zahlung mit Karte beim Check-in.",
        "es": "Precio total: {amount} € — pago con tarjeta en el check-in.",
        "fr": "Prix total : {amount} € — paiement par carte à l’arrivée.",
    },
    Invoice.PaymentMethod.TRANSFER: {
        "hr": "Ukupna cijena: {amount} € — plaćanje transakcijskim računom (prema dogovoru).",
        "en": "Total price: €{amount} — payment by bank transfer (as agreed).",
        "de": "Gesamtpreis: {amount} € — Zahlung per Banküberweisung (wie vereinbart).",
        "es": "Precio total: {amount} € — pago por transferencia bancaria (según acuerdo).",
        "fr": "Prix total : {amount} € — paiement par virement bancaire (selon accord).",
    },
    Invoice.PaymentMethod.OTHER: {
        "hr": "Ukupna cijena: {amount} €.",
        "en": "Total price: €{amount}.",
        "de": "Gesamtpreis: {amount} €.",
        "es": "Precio total: {amount} €.",
        "fr": "Prix total : {amount} €.",
    },
}

from apps.communications.guest_compose_defaults import (
    ADDRESS_LABEL,
    AUTOCHECKIN_WA_ME_PREFILL,
    AUTOCHECKIN_WHATSAPP_INTRO_HEAD,
    AUTOCHECKIN_WHATSAPP_INTRO_TAIL,
    CHECKIN_AUTOMATION_FAILED,
    CHECKIN_LINE,
    CHECKIN_PARTIAL_DOCUMENTS,
    CHECKIN_READY_BODY,
    DEFAULT_ADDRESS,
    DEFAULT_GUEST_NAME,
    DOCUMENTS_BATCH_CONFIRM,
    DOCUMENTS_BATCH_CONFIRM_NO,
    DOCUMENTS_BATCH_CONFIRM_YES,
    DOCUMENTS_TEXTS,
    ENTRANCE_IMAGE_CAPTION,
    ENTRANCE_TEXTS,
    EVISITOR_REGISTERED,
    GREETING,
    MAPS_LINK,
    MISSING_ID_SIDE_LABEL_NATIONAL_BACK,
    MISSING_ID_SIDE_LABEL_NATIONAL_FRONT,
    MISSING_ID_SIDE_LABEL_PASSPORT,
    MISSING_ID_SIDE_LINE,
    MISSING_ID_SIDES_INTRO,
    OPERATOR_CHECKIN_COMPLETE_BODY,
    PARKING_TEXTS,
    POST_CHECKIN_ARRIVAL_THANKS,
    POST_CHECKIN_PARKING,
    POST_CHECKIN_WELCOME_EVENING,
    POST_CHECKIN_WELCOME_TODAY,
    RESERVATION_HEADER,
    ROOM_LABEL,
    SIGN_OFF,
    THANKS,
)
from apps.properties.guest_info import (
    build_guest_facts_for_llm,
    format_wifi_block,
    guest_maps_url,
    guest_text,
)

def _text_for_lang(texts: dict[str, str], lang: str) -> str:
    return texts.get(lang) or texts["en"]


def _property_guest_text(
    reservation: Reservation,
    key: str,
    lang: str,
    **fmt: object,
) -> str:
    return guest_text(reservation.property, key, lang, **fmt)


def _wifi_section(reservation: Reservation, lang: str) -> str:
    return format_wifi_block(reservation.property, lang)


def _message_lines_before_signoff(
    reservation: Reservation,
    context: dict,
    *,
    body_lines: list[str],
) -> str:
    """Body lines, optional WiFi block, sign-off, property name, footer."""
    lang = context["language"]
    lines = list(body_lines)
    wifi = _wifi_section(reservation, lang)
    if wifi:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(wifi)
    lines.extend(
        [
            "",
            _text_for_lang(SIGN_OFF, lang),
            context["property_name"],
            "",
            FOOTER,
        ]
    )
    return "\n".join(line for line in lines if line is not None)


def _normalize_hint(hint: str) -> str:
    return " ".join((hint or "").strip().lower().split())


def _lang_key(reservation: Reservation, override: str | None = None) -> str:
    return compose_language_for_reservation(reservation, override)


def tenant_language_for_reservation(reservation: Reservation) -> str:
    return normalize_app_language(
        getattr(reservation.tenant, "default_language", None) or "hr"
    )


def body_text_for_tenant_preview(
    reservation: Reservation,
    guest_body: str,
    guest_lang: str,
) -> tuple[str, str]:
    """Return (tenant_language, body_text_tenant) for compose UI preview."""
    tenant_lang = tenant_language_for_reservation(reservation)
    body = (guest_body or "").strip()
    if not body:
        return tenant_lang, ""
    guest_base = (guest_lang or "").split("-")[0].lower()
    if guest_base == tenant_lang:
        return tenant_lang, body
    if not translation_available():
        return tenant_lang, body
    return tenant_lang, translate_text(body, tenant_lang)


def build_compose_response_fields(
    reservation: Reservation,
    *,
    body_text: str,
    guest_language: str,
) -> dict[str, str]:
    tenant_lang, body_tenant = body_text_for_tenant_preview(
        reservation,
        body_text,
        guest_language,
    )
    return {
        "body_text_tenant": body_tenant,
        "tenant_language": tenant_lang,
    }


def _format_amount(amount: Decimal | None) -> str:
    if amount is None:
        return "0,00"
    return f"{amount:.2f}".replace(".", ",")


def _payment_text(reservation: Reservation, lang: str) -> str:
    method = resolve_payment_method(reservation)
    templates = PAYMENT_TEXTS.get(method, PAYMENT_TEXTS[Invoice.PaymentMethod.OTHER])
    template = _text_for_lang(templates, lang)
    return template.format(amount=_format_amount(reservation.amount))


def _property_address(reservation: Reservation) -> str:
    addr = (reservation.property.address or "").strip()
    return addr or DEFAULT_ADDRESS


def _adults_count(reservation: Reservation) -> int:
    if reservation.adults_count:
        return reservation.adults_count
    count = reservation.guests.count()
    return max(1, count)


def _message_history(reservation: Reservation, limit: int = 10) -> list[dict]:
    rows: list[tuple[str, str, str, str]] = []

    for msg in WhatsAppMessage.objects.filter(reservation=reservation).order_by("-created_at")[:limit]:
        rows.append(
            (
                msg.created_at.isoformat(),
                "whatsapp",
                msg.direction,
                (msg.body or "").strip(),
            )
        )

    for msg in ChannexMessage.objects.filter(reservation=reservation).order_by("-created_at")[:limit]:
        direction = "inbound" if msg.sender == ChannexMessage.Sender.GUEST else "outbound"
        rows.append(
            (
                msg.created_at.isoformat(),
                "booking",
                direction,
                (msg.body or "").strip(),
            )
        )

    rows.sort(key=lambda r: r[0], reverse=True)
    return [
        {"at": at, "channel": channel, "direction": direction, "body": body}
        for at, channel, direction, body in rows[:limit]
        if body
    ]


def build_compose_context(
    reservation: Reservation,
    *,
    language: str | None = None,
) -> dict:
    email_ctx = _email_context(reservation)
    lang = _lang_key(reservation, language)
    prop = reservation.property
    contact = prop.contact if isinstance(prop.contact, dict) else {}

    return {
        "language": lang,
        "guest_name": reservation.booker_name or "",
        "booking_code": reservation.booking_code or reservation.external_id or "",
        "property_name": reservation.property.name,
        "room_label": email_ctx.get("room_label") or "",
        "check_in_date": reservation.check_in.isoformat(),
        "check_in": email_ctx["check_in_display"],
        "check_out": email_ctx["check_out_display"],
        "check_in_time": email_ctx["check_in_time"],
        "check_out_time": email_ctx["check_out_time"],
        "adults_count": _adults_count(reservation),
        "amount": _format_amount(reservation.amount),
        "currency": reservation.currency or "EUR",
        "payment_text": _payment_text(reservation, lang),
        "address": _property_address(reservation),
        "maps_link": guest_maps_url(prop),
        "guest_facts": build_guest_facts_for_llm(prop, lang),
        "notes": (reservation.notes or "").strip(),
        "contact_phone": (contact.get("phone") or "").strip(),
        "message_history": _message_history(reservation),
    }


def _render_checkin_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    name = context["guest_name"] or _text_for_lang(DEFAULT_GUEST_NAME, lang)
    adults = context["adults_count"]
    entrance = _property_guest_text(reservation, "entrance", lang)
    parking = _property_guest_text(reservation, "parking", lang)
    documents = _property_guest_text(reservation, "documents", lang, adults=adults)
    checkin_line = _property_guest_text(
        reservation,
        "checkin_line",
        lang,
        check_in=context["check_in_date"],
        check_in_time=context["check_in_time"],
    )

    lines = [
        _text_for_lang(GREETING, lang).format(name=name),
        "",
        _text_for_lang(THANKS, lang).format(property_name=context["property_name"]),
        "",
        _text_for_lang(RESERVATION_HEADER, lang),
        f"• {context['booking_code']}" if context["booking_code"] else "",
        f"• {context['property_name']}",
    ]
    if context["room_label"]:
        lines.append(f"• {_text_for_lang(ROOM_LABEL, lang)}: {context['room_label']}")
    lines.extend(
        [
            f"• {context['check_in']} – {context['check_out']}",
            f"• {context['payment_text']}",
            "",
            checkin_line,
            "",
            _text_for_lang(ADDRESS_LABEL, lang),
            context["address"],
            context["maps_link"],
            "",
            entrance,
            "",
            parking,
            "",
            documents,
            "",
            _text_for_lang(SIGN_OFF, lang),
            context["property_name"],
            "",
            FOOTER,
        ]
    )
    return "\n".join(line for line in lines if line is not None)


def _render_checkin_ready_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    body = _property_guest_text(reservation, "checkin_ready", lang)
    return "\n".join(
        [
            body,
            "",
            _text_for_lang(SIGN_OFF, lang),
            context["property_name"],
            "",
            FOOTER,
        ]
    )


def render_checkin_ready_message(reservation: Reservation) -> str:
    """Deterministic post-apply thank-you message (same as compose checkin ready)."""
    context = build_compose_context(reservation)
    return _render_checkin_ready_fallback(reservation, context)


def render_post_checkin_guest_reply(
    reservation: Reservation,
    *,
    mentions_arrival: bool,
    mentions_parking: bool,
    evening_welcome: bool,
) -> str:
    """Auto-reply after documents are complete (parking / arrival questions)."""
    context = build_compose_context(reservation)
    lang = context["language"]
    raw_name = (context["guest_name"] or "").strip()
    first_name = raw_name.split()[0] if raw_name else _text_for_lang(DEFAULT_GUEST_NAME, lang)
    property_name = context["property_name"]

    lines = [_text_for_lang(GREETING, lang).format(name=first_name), ""]
    if mentions_arrival:
        lines.append(_property_guest_text(reservation, "post_checkin_arrival_thanks", lang))
        lines.append("")
    if mentions_parking:
        lines.append(_property_guest_text(reservation, "parking_post_checkin", lang))
        lines.append("")
    welcome_key = "post_checkin_welcome_evening" if evening_welcome else "post_checkin_welcome_today"
    lines.append(_property_guest_text(reservation, welcome_key, lang, property_name=property_name))
    wifi = _wifi_section(reservation, lang)
    if wifi:
        lines.extend(["", wifi])
    lines.extend(
        [
            "",
            _text_for_lang(SIGN_OFF, lang),
            property_name,
            "",
            FOOTER,
        ]
    )
    return "\n".join(lines)


def render_entrance_image_caption(reservation: Reservation) -> str:
    lang = _lang_key(reservation)
    return _property_guest_text(reservation, "entrance_image_caption", lang)


def _render_operator_checkin_complete_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    body = _property_guest_text(reservation, "operator_checkin_complete", lang)
    return _message_lines_before_signoff(reservation, context, body_lines=[body])


def render_operator_checkin_complete_message(reservation: Reservation) -> str:
    """Email after reception staff completes on-site check-in via WhatsApp operator flow."""
    context = build_compose_context(reservation)
    return _render_operator_checkin_complete_fallback(reservation, context)


def autocheckin_wa_me_prefill(language: str, reservation: Reservation | None = None) -> str:
    lang = _lang_key_from_code(language)
    if reservation is not None:
        return _property_guest_text(reservation, "autocheckin_wa_me_prefill", lang)
    return AUTOCHECKIN_WA_ME_PREFILL.get(lang, AUTOCHECKIN_WA_ME_PREFILL["en"])


def _autocheckin_intro_booking_code(reservation: Reservation, context: dict) -> str:
    return context["booking_code"] or str(reservation.pk)


def _autocheckin_intro_cta_label(reservation: Reservation, lang: str) -> str:
    return autocheckin_wa_me_prefill(lang, reservation=reservation)


def _autocheckin_intro_plain_cta_line(*, reservation: Reservation, lang: str, wa_link: str) -> str:
    label = _autocheckin_intro_cta_label(reservation, lang)
    link = (wa_link or "").strip()
    return f"{label}: {link}" if link else label


def _whatsapp_cta_button_html(*, href: str, label: str) -> str:
    href_esc = html.escape(href, quote=True)
    label_esc = html.escape(label)
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0">'
        "<tr><td>"
        f'<a href="{href_esc}" '
        'style="display:inline-block;padding:12px 24px;background-color:#25D366;'
        'color:#ffffff;text-decoration:none;font-weight:bold;">'
        f"{label_esc}</a>"
        "</td></tr></table>"
    )


def _render_autocheckin_intro_core(
    *,
    reservation: Reservation,
    lang: str,
    display_phone: str,
    booking_code: str,
    cta_line: str,
) -> str:
    head = _property_guest_text(
        reservation,
        "autocheckin_whatsapp_intro_head",
        lang,
        display_phone=display_phone or "",
    )
    tail = _property_guest_text(
        reservation,
        "autocheckin_whatsapp_intro_tail",
        lang,
        booking_code=booking_code,
    )
    return "\n\n".join(part for part in (head, cta_line, tail) if part)


def render_autocheckin_whatsapp_intro_email(
    reservation: Reservation,
    *,
    wa_link: str,
    display_phone: str,
) -> str:
    context = build_compose_context(reservation)
    lang = context["language"]
    body = _render_autocheckin_intro_core(
        reservation=reservation,
        lang=lang,
        display_phone=display_phone or "",
        booking_code=_autocheckin_intro_booking_code(reservation, context),
        cta_line=_autocheckin_intro_plain_cta_line(reservation=reservation, lang=lang, wa_link=wa_link),
    )
    return "\n".join(
        [
            body,
            "",
            _text_for_lang(SIGN_OFF, lang),
            context["property_name"],
            "",
            FOOTER,
        ]
    )


def render_autocheckin_whatsapp_intro_email_html(
    reservation: Reservation,
    *,
    wa_link: str,
    display_phone: str,
) -> str:
    context = build_compose_context(reservation)
    lang = context["language"]
    booking_code = _autocheckin_intro_booking_code(reservation, context)
    phone = html.escape(display_phone or "")
    code = html.escape(booking_code)
    property_name = html.escape(context["property_name"] or "")
    sign_off = html.escape(_text_for_lang(SIGN_OFF, lang))
    footer = html.escape(FOOTER)

    head = html.escape(
        _property_guest_text(
            reservation,
            "autocheckin_whatsapp_intro_head",
            lang,
            display_phone=display_phone or "",
        )
    ).replace("\n\n", "<br><br>")
    tail_raw = _property_guest_text(
        reservation,
        "autocheckin_whatsapp_intro_tail",
        lang,
        booking_code=booking_code,
    )
    tail_parts = tail_raw.split("\n\n", 1)
    utility_note = html.escape(tail_parts[0])
    booking_line = html.escape(tail_parts[1]) if len(tail_parts) > 1 else ""
    if booking_code and booking_line:
        booking_line = booking_line.replace(
            html.escape(booking_code),
            f"<strong>{html.escape(booking_code)}</strong>",
            1,
        )
    cta = _whatsapp_cta_button_html(
        href=wa_link or "",
        label=_autocheckin_intro_cta_label(reservation, lang),
    )

    return "\n".join(
        [
            f"<p>{head}</p>",
            f"<p>{cta}</p>",
            f"<p>{utility_note}</p>",
            f"<p>{booking_line}</p>" if booking_line else "",
            f"<p>{sign_off}<br>{property_name}</p>",
            f'<p style="color:#666;font-size:12px;">{footer}</p>',
        ]
    )


def _lang_key_from_code(language: str) -> str:
    base = (language or "en").split("-")[0].lower()
    if base in SUPPORTED_COMPOSE_LANGS:
        return base
    return "en"


def _render_evisitor_registered_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    body = _property_guest_text(reservation, "evisitor_registered", lang)
    return _message_lines_before_signoff(reservation, context, body_lines=[body])


def render_evisitor_registered_message(reservation: Reservation) -> str:
    """WhatsApp message after all required guests are registered in eVisitor."""
    context = build_compose_context(reservation)
    return _render_evisitor_registered_fallback(reservation, context)


def _render_documents_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    adults = context["adults_count"]
    documents = _property_guest_text(reservation, "documents", lang, adults=adults)
    return "\n".join(
        [
            documents,
            "",
            _text_for_lang(SIGN_OFF, lang),
            context["property_name"],
            "",
            FOOTER,
        ]
    )


def render_documents_message(reservation: Reservation) -> str:
    """Document upload instructions after Auto check-in quick reply."""
    context = build_compose_context(reservation)
    return _render_documents_fallback(reservation, context)


def render_documents_batch_confirm_message(reservation: Reservation) -> str:
    context = build_compose_context(reservation)
    return _property_guest_text(reservation, "documents_batch_confirm", context["language"])


def documents_batch_confirm_button_labels(reservation: Reservation) -> tuple[str, str]:
    context = build_compose_context(reservation)
    lang = context["language"]
    return (
        _property_guest_text(reservation, "documents_batch_confirm_yes", lang),
        _property_guest_text(reservation, "documents_batch_confirm_no", lang),
    )


def _render_checkin_partial_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    body = _property_guest_text(reservation, "checkin_partial_documents", lang)
    return "\n".join(
        [
            body,
            "",
            _text_for_lang(SIGN_OFF, lang),
            context["property_name"],
            "",
            FOOTER,
        ]
    )


def render_checkin_partial_documents_message(reservation: Reservation) -> str:
    context = build_compose_context(reservation)
    return _render_checkin_partial_fallback(reservation, context)


def _missing_id_side_label(*, reservation: Reservation, lang: str, gap: MissingIdSide) -> str:
    if gap.is_passport:
        return _property_guest_text(reservation, "missing_id_side_label_passport", lang)
    if gap.side == "back":
        return _property_guest_text(reservation, "missing_id_side_label_national_back", lang)
    return _property_guest_text(reservation, "missing_id_side_label_national_front", lang)


def _render_missing_id_sides_fallback(reservation: Reservation, context: dict, gaps: list[MissingIdSide]) -> str:
    lang = context["language"]
    line_template = _property_guest_text(reservation, "missing_id_side_line", lang)
    lines = [
        _property_guest_text(reservation, "missing_id_sides_intro", lang),
        "",
        *[
            line_template.format(name=gap.guest_name, side_label=_missing_id_side_label(reservation=reservation, lang=lang, gap=gap))
            for gap in gaps
        ],
        "",
        _text_for_lang(SIGN_OFF, lang),
        context["property_name"],
        "",
        FOOTER,
    ]
    return "\n".join(lines)


def render_missing_id_sides_message(reservation: Reservation, gaps: list[MissingIdSide]) -> str:
    context = build_compose_context(reservation)
    return _render_missing_id_sides_fallback(reservation, context, gaps)


def _render_checkin_automation_failed_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    body = _property_guest_text(reservation, "checkin_automation_failed", lang)
    return "\n".join(
        [
            body,
            "",
            _text_for_lang(SIGN_OFF, lang),
            context["property_name"],
            "",
            FOOTER,
        ]
    )


def render_checkin_automation_failed_message(reservation: Reservation) -> str:
    context = build_compose_context(reservation)
    return _render_checkin_automation_failed_fallback(reservation, context)


def _render_autocheckin_waived_fallback(reservation: Reservation, context: dict) -> str:
    lang = context["language"]
    raw_name = (context["guest_name"] or "").strip()
    first_name = raw_name.split()[0] if raw_name else _text_for_lang(DEFAULT_GUEST_NAME, lang)
    property_name = context["property_name"]
    body = _property_guest_text(
        reservation,
        "autocheckin_waived",
        lang,
        first_name=first_name,
        property_name=property_name,
    )
    return "\n".join(
        [
            body,
            "",
            _text_for_lang(SIGN_OFF, lang),
            property_name,
            "",
            FOOTER,
        ]
    )


def render_autocheckin_waived_message(reservation: Reservation) -> str:
    context = build_compose_context(reservation)
    return _render_autocheckin_waived_fallback(reservation, context)


def render_arrival_thanks_message(reservation: Reservation) -> str:
    """Short thanks when guest shares arrival time (waived auto check-in flow)."""
    context = build_compose_context(reservation)
    lang = context["language"]
    property_name = context["property_name"]
    body = _property_guest_text(reservation, "post_checkin_arrival_thanks", lang)
    return "\n".join(
        [
            body,
            "",
            _text_for_lang(SIGN_OFF, lang),
            property_name,
            "",
            FOOTER,
        ]
    )


def _system_prompt() -> str:
    return (
        "You are a professional hotel reception assistant drafting short guest messages. "
        "Use ONLY facts from the JSON context. Never invent prices, dates, room names, or policies. "
        "Match the requested language. Keep a warm, concise reception tone. "
        "End with the property name and this footer on its own line: "
        "Managed by stay.hr — https://stay.hr/"
    )


def _user_prompt(intent: str, hint: str, context: dict) -> str:
    payload = {
        "intent": intent,
        "hint": hint,
        "context": context,
    }
    instructions = {
        GuestMessageIntent.REPLY: "Write a reply to the guest using message_history; address their latest inbound message.",
        GuestMessageIntent.CUSTOM: "Write a custom message following the hint.",
    }
    task = instructions.get(intent, instructions[GuestMessageIntent.CUSTOM])
    return (
        f"Task: {task}\n"
        f"Language: {context['language']}\n"
        f"Data (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _generate_body(
    reservation: Reservation,
    intent: str,
    hint: str,
    language: str | None,
) -> tuple[str, bool, str]:
    context = build_compose_context(reservation, language=language)

    if intent == GuestMessageIntent.CHECKIN:
        return _render_checkin_fallback(reservation, context), False, ""

    if intent == GuestMessageIntent.REPLY and _normalize_hint(hint) == HINT_CHECKIN_READY:
        return _render_checkin_ready_fallback(reservation, context), False, ""

    if intent == GuestMessageIntent.REPLY and _normalize_hint(hint) == HINT_EVISITOR_REGISTERED:
        return _render_evisitor_registered_fallback(reservation, context), False, ""

    if intent == GuestMessageIntent.REPLY and _normalize_hint(hint) == HINT_ID_MISSING_SIDES:
        from apps.reservations.document_intake_sides import find_missing_id_sides

        gaps = find_missing_id_sides(reservation)
        return _render_missing_id_sides_fallback(reservation, context, gaps), False, ""

    used_llm = False
    model_name = ""

    if llm_configured():
        try:
            body = complete_chat(_system_prompt(), _user_prompt(intent, hint, context))
            used_llm = True
            model_name = llm_model()
            return body, used_llm, model_name
        except GuestComposeError:
            logger.warning(
                "LLM compose failed, using fallback",
                extra={"reservation_id": reservation.pk, "intent": intent},
            )

    fallback_hint = hint.strip() or {
        GuestMessageIntent.REPLY: "Thank you for your message. We will get back to you shortly.",
        GuestMessageIntent.CUSTOM: "Thank you for your message.",
    }.get(intent, "Thank you for your message.")
    lang = context["language"]
    greeting = _text_for_lang(GREETING, lang).format(
        name=context["guest_name"] or _text_for_lang(DEFAULT_GUEST_NAME, lang)
    )
    return f"{greeting}\n\n{fallback_hint}\n\n{FOOTER}", used_llm, model_name


def create_draft_from_body_text(
    reservation: Reservation,
    body_text: str,
    *,
    api_application: ApiApplication | None = None,
) -> tuple[GuestMessageDraft, dict]:
    """Create a draft from exact text (resend / relay) without LLM."""
    text = (body_text or "").strip()
    if not text:
        raise ValueError("body_text is required")

    lang = _lang_key(reservation, None)
    channels = build_message_channels(reservation)
    draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.CUSTOM,
        hint="resend",
        llm_body_text=text,
        final_body_text="",
        language=lang,
        llm_model="",
        prompt_version=prompt_version(),
        api_application=api_application,
    )
    return draft, channels


def compose_guest_message(
    reservation: Reservation,
    *,
    intent: str,
    hint: str = "",
    api_application: ApiApplication | None = None,
    language: str | None = None,
) -> tuple[GuestMessageDraft, dict, bool]:
    """
    Compose message, persist draft, return (draft, channels, llm_used).
    """
    if intent not in {c.value for c in GuestMessageIntent}:
        raise ValueError(f"Invalid intent: {intent}")

    body, llm_used, model_name = _generate_body(reservation, intent, hint, language)
    lang = _lang_key(reservation, language)
    channels = build_message_channels(reservation)

    draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=intent,
        hint=(hint or "").strip(),
        llm_body_text=body,
        final_body_text="",
        language=lang,
        llm_model=model_name,
        prompt_version=prompt_version(),
        api_application=api_application,
    )
    return draft, channels, llm_used


def smoke_test_llm() -> dict:
    """Quick connectivity check for production shell."""
    if not llm_configured():
        return {"ok": False, "reason": "not_configured"}
    try:
        text = complete_chat(
            "Reply with exactly: OK",
            "Ping",
            timeout=15.0,
        )
        return {"ok": text.strip().upper().startswith("OK"), "sample": text[:80]}
    except GuestComposeError as exc:
        return {"ok": False, "reason": str(exc)}
