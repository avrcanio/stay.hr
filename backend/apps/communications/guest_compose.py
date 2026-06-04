"""LLM guest message compose with deterministic fallback."""

from __future__ import annotations

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
from apps.billing.models import Invoice
from apps.billing.services.payment import resolve_payment_method
from apps.communications.guest_email import _email_context, _language_for_reservation
from apps.communications.guest_message_send import build_message_channels
from apps.communications.models import GuestMessageDraft, GuestMessageIntent
from apps.integrations.models import ChannexMessage, WhatsAppMessage
from apps.reservations.models import Reservation
from apps.tenants.models import ApiApplication

logger = logging.getLogger(__name__)

MAPS_LINK = "https://maps.app.goo.gl/BN15CcMmmAapmjUs7"
DEFAULT_ADDRESS = "Ul. bana Josipa Jelačića 58, 22000 Šibenik"

PAYMENT_TEXTS: dict[str, dict[str, str]] = {
    Invoice.PaymentMethod.BOOKING: {
        "hr": "Ukupna cijena: {amount} € — plaćeno u cijelosti putem Booking.com (Payments by Booking.com). Boravak ne plaćate na check-inu.",
        "en": "Total price: €{amount} — paid in full via Booking.com (Payments by Booking.com). No payment due for your stay at check-in.",
        "de": "Gesamtpreis: {amount} € — vollständig über Booking.com (Payments by Booking.com) bezahlt. Keine Zahlung für den Aufenthalt beim Check-in.",
        "ro": "Preț total: {amount} € — plătit integral prin Booking.com (Payments by Booking.com). Nu este necesară plata cazării la check-in.",
    },
    Invoice.PaymentMethod.CASH: {
        "hr": "Ukupna cijena: {amount} € — plaćanje gotovinom na check-inu.",
        "en": "Total price: €{amount} — payment in cash at check-in.",
        "de": "Gesamtpreis: {amount} € — Zahlung bar beim Check-in.",
        "ro": "Preț total: {amount} € — plata cash la check-in.",
    },
    Invoice.PaymentMethod.CARD: {
        "hr": "Ukupna cijena: {amount} € — plaćanje karticom na check-inu.",
        "en": "Total price: €{amount} — payment by card at check-in.",
        "de": "Gesamtpreis: {amount} € — Zahlung mit Karte beim Check-in.",
        "ro": "Preț total: {amount} € — plata cu cardul la check-in.",
    },
    Invoice.PaymentMethod.TRANSFER: {
        "hr": "Ukupna cijena: {amount} € — plaćanje transakcijskim računom (prema dogovoru).",
        "en": "Total price: €{amount} — payment by bank transfer (as agreed).",
        "de": "Gesamtpreis: {amount} € — Zahlung per Banküberweisung (wie vereinbart).",
        "ro": "Preț total: {amount} € — plată prin transfer bancar (conform acordului).",
    },
    Invoice.PaymentMethod.OTHER: {
        "hr": "Ukupna cijena: {amount} €.",
        "en": "Total price: €{amount}.",
        "de": "Gesamtpreis: {amount} €.",
        "ro": "Preț total: {amount} €.",
    },
}

ENTRANCE_TEXTS = {
    "hr": (
        'Ulaz: potražite natpis „Restaurant Uzorita” i broj **58** na bijelom zidu — '
        "kapija s vinovom lozom odmah desno od znaka. "
        "(Fotografiju ulaza šaljemo u sljedećoj poruci.)"
    ),
    "en": (
        'Entrance: look for the "Restaurant Uzorita" sign and house number **58** on the white wall — '
        "the gate with vines is just to the right of the sign. "
        "(We'll send a photo of the entrance in the next message.)"
    ),
    "de": (
        "Eingang: Schild „Restaurant Uzorita” und Hausnummer **58** an der weißen Mauer — "
        "das Tor mit Weinreben rechts neben dem Schild. "
        "(Ein Foto des Eingangs folgt in der nächsten Nachricht.)"
    ),
    "ro": (
        "Intrare: căutați panoul „Restaurant Uzorita” și numărul **58** pe peretele alb — "
        "poarta cu viță de vie imediat la dreapta panoului. "
        "(Trimitem fotografia intrării în mesajul următor.)"
    ),
}

DOCUMENTS_TEXTS = {
    "hr": (
        "Molimo prije dolaska pošaljite nam ovdje na WhatsApp fotografije dokumenata "
        "za svakog odraslog gosta ({adults}): putovnica (stranica s podacima) ili "
        "osobna iskaznica (prednja + stražnja strana). Bez bljeskalice, cijeli dokument u kadru. "
        "Podatke koristimo isključivo za zakonsku prijavu boravka (eVisitor)."
    ),
    "en": (
        "Please send us photos of ID documents here on WhatsApp before arrival — "
        "one set per adult guest ({adults}): passport (biodata page) or national ID card "
        "(front + back). No flash, full document in frame. "
        "We use this data only for mandatory guest registration (eVisitor)."
    ),
    "de": (
        "Bitte senden Sie uns vor der Anreise Fotos der Ausweisdokumente hier per WhatsApp — "
        "pro erwachsenem Gast ({adults}): Reisepass (Datenseite) oder Personalausweis "
        "(Vorder- und Rückseite). Ohne Blitz, ganzes Dokument im Bild. "
        "Die Daten verwenden wir ausschließlich für die gesetzliche Meldepflicht (eVisitor)."
    ),
    "ro": (
        "Vă rugăm să ne trimiteți pe WhatsApp, înainte de sosire, fotografii ale actelor de identitate — "
        "câte un set pentru fiecare adult ({adults}): pașaport (pagina cu date) sau carte de identitate "
        "(față + verso). Fără bliț, documentul complet în cadru. "
        "Datele sunt folosite exclusiv pentru înregistrarea legală a șederii (eVisitor)."
    ),
}

CHECKIN_LINE = {
    "hr": "Check-in: {check_in} od {check_in_time}",
    "en": "Check-in: {check_in} from {check_in_time}",
    "de": "Check-in: {check_in} ab {check_in_time} Uhr",
    "ro": "Check-in: {check_in}, de la ora {check_in_time}",
}

GREETING = {
    "hr": "Bok {name}!",
    "en": "Hi {name}!",
    "de": "Hallo {name}!",
    "ro": "Bună {name}!",
}

THANKS = {
    "hr": "Hvala na rezervaciji u {property_name}.",
    "en": "Thank you for your booking at {property_name}.",
    "de": "Vielen Dank für Ihre Buchung bei {property_name}.",
    "ro": "Vă mulțumim pentru rezervarea la {property_name}.",
}

RESERVATION_HEADER = {
    "hr": "Vaša rezervacija",
    "en": "Your reservation",
    "de": "Ihre Buchung",
    "ro": "Rezervarea dvs.",
}

FOOTER = "Managed by stay.hr — https://stay.hr/"


def _lang_key(reservation: Reservation, override: str | None = None) -> str:
    if override:
        base = override.split("-")[0].lower()
        if base in ("hr", "en", "de", "ro"):
            return base
    lang = _language_for_reservation(reservation)
    return lang if lang in ("hr", "en", "de", "ro") else "en"


def _format_amount(amount: Decimal | None) -> str:
    if amount is None:
        return "0,00"
    return f"{amount:.2f}".replace(".", ",")


def _payment_text(reservation: Reservation, lang: str) -> str:
    method = resolve_payment_method(reservation)
    templates = PAYMENT_TEXTS.get(method, PAYMENT_TEXTS[Invoice.PaymentMethod.OTHER])
    template = templates.get(lang) or templates["en"]
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
        "check_in": email_ctx["check_in_display"],
        "check_out": email_ctx["check_out_display"],
        "check_in_time": email_ctx["check_in_time"],
        "check_out_time": email_ctx["check_out_time"],
        "adults_count": _adults_count(reservation),
        "amount": _format_amount(reservation.amount),
        "currency": reservation.currency or "EUR",
        "payment_text": _payment_text(reservation, lang),
        "address": _property_address(reservation),
        "maps_link": MAPS_LINK,
        "notes": (reservation.notes or "").strip(),
        "contact_phone": (contact.get("phone") or "").strip(),
        "message_history": _message_history(reservation),
    }


def _render_checkin_fallback(context: dict) -> str:
    lang = context["language"]
    name = context["guest_name"] or ("Gost" if lang == "hr" else "Guest")
    adults = context["adults_count"]
    entrance = ENTRANCE_TEXTS.get(lang, ENTRANCE_TEXTS["en"])
    documents = DOCUMENTS_TEXTS.get(lang, DOCUMENTS_TEXTS["en"]).format(adults=adults)
    checkin_line = CHECKIN_LINE.get(lang, CHECKIN_LINE["en"]).format(
        check_in=context["check_in"],
        check_in_time=context["check_in_time"],
    )

    lines = [
        GREETING.get(lang, GREETING["en"]).format(name=name),
        "",
        THANKS.get(lang, THANKS["en"]).format(property_name=context["property_name"]),
        "",
        RESERVATION_HEADER.get(lang, RESERVATION_HEADER["en"]),
        f"• {context['booking_code']}" if context["booking_code"] else "",
        f"• {context['property_name']}",
    ]
    if context["room_label"]:
        room_label = {"hr": "Soba", "en": "Room", "de": "Zimmer", "ro": "Cameră"}.get(lang, "Room")
        lines.append(f"• {room_label}: {context['room_label']}")
    lines.extend(
        [
            f"• {context['check_in']} – {context['check_out']}",
            f"• {context['payment_text']}",
            "",
            checkin_line,
            "",
            {"hr": "Adresa", "en": "Address", "de": "Adresse", "ro": "Adresă"}.get(lang, "Address"),
            context["address"],
            context["maps_link"],
            "",
            entrance,
            "",
            documents,
            "",
            {
                "hr": "Javite nam okvirno vrijeme dolaska kad pošaljete dokumente.",
                "en": "Let us know your approximate arrival time when you send the documents.",
                "de": "Teilen Sie uns ungefähre Ankunftszeit mit, wenn Sie die Dokumente senden.",
                "ro": "Anunțați-ne ora aproximativă de sosire când trimiteți documentele.",
            }.get(lang, ""),
            "",
            {
                "hr": "Lijep pozdrav,",
                "en": "Best regards,",
                "de": "Mit freundlichen Grüßen,",
                "ro": "Cu stimă,",
            }.get(lang, ""),
            context["property_name"],
            "",
            FOOTER,
        ]
    )
    return "\n".join(line for line in lines if line is not None)


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
        GuestMessageIntent.CHECKIN: "Write a pre-arrival check-in message with reservation details, address, payment info, entrance note, and document request.",
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

    if intent == GuestMessageIntent.CHECKIN:
        return _render_checkin_fallback(context), used_llm, model_name

    fallback_hint = hint.strip() or {
        GuestMessageIntent.REPLY: "Thank you for your message. We will get back to you shortly.",
        GuestMessageIntent.CUSTOM: "Thank you for your message.",
    }.get(intent, "Thank you for your message.")
    lang = context["language"]
    greeting = GREETING.get(lang, GREETING["en"]).format(
        name=context["guest_name"] or ("Gost" if lang == "hr" else "Guest")
    )
    return f"{greeting}\n\n{fallback_hint}\n\n{FOOTER}", used_llm, model_name


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
