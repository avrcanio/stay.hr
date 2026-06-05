"""Guest message compose with deterministic check-in templates and optional LLM."""

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
from apps.communications.guest_compose_language import compose_language_for_reservation
from apps.communications.guest_email import _email_context
from apps.communications.guest_message_send import build_message_channels
from apps.communications.models import GuestMessageDraft, GuestMessageIntent
from apps.integrations.models import ChannexMessage, WhatsAppMessage
from apps.reservations.models import Reservation
from apps.tenants.models import ApiApplication

logger = logging.getLogger(__name__)

HINT_CHECKIN_READY = "checkin ready"

MAPS_LINK = "https://maps.app.goo.gl/BN15CcMmmAapmjUs7"
DEFAULT_ADDRESS = "Ul. bana Josipa Jelačića 58, 22000 Šibenik"

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
    "es": (
        'Entrada: busque el cartel «Restaurant Uzorita» y el número **58** en la pared blanca — '
        "la puerta con hiedra está justo a la derecha del cartel. "
        "(Enviaremos una foto de la entrada en el siguiente mensaje.)"
    ),
    "fr": (
        "Entrée : repérez l’enseigne « Restaurant Uzorita » et le numéro **58** sur le mur blanc — "
        "le portail avec la vigne est juste à droite de l’enseigne. "
        "(Nous enverrons une photo de l’entrée dans le message suivant.)"
    ),
}

PARKING_TEXTS = {
    "hr": (
        "Parkiranje: u cijeloj zoni parkiranje je besplatno. "
        "Možete parkirati odmah ispred objekta; ako nema mjesta, slobodno bilo gdje u neposrednoj blizini."
    ),
    "en": (
        "Parking: parking is free throughout the zone. "
        "You can park right in front of the property; if there is no space, anywhere nearby is fine."
    ),
    "de": (
        "Parken: In der gesamten Zone ist das Parken kostenlos. "
        "Sie können direkt vor dem Haus parken; wenn kein Platz frei ist, finden Sie problemlos einen Parkplatz in unmittelbarer Nähe."
    ),
    "es": (
        "Aparcamiento: el aparcamiento es gratuito en toda la zona. "
        "Puede aparcar justo delante del alojamiento; si no hay sitio, en cualquier lugar cercano."
    ),
    "fr": (
        "Stationnement : le stationnement est gratuit dans toute la zone. "
        "Vous pouvez vous garer juste devant l’établissement ; s’il n’y a pas de place, n’importe où à proximité."
    ),
}

DOCUMENTS_TEXTS = {
    "hr": (
        "Check-in — dokumenti\n"
        "Molimo prije dolaska pošaljite nam ovdje na WhatsApp fotografije dokumenata "
        "za svakog odraslog gosta ({adults}): putovnica (stranica s podacima) ili "
        "osobna iskaznica (prednja + stražnja strana). Bez bljeskalice, cijeli dokument u kadru. "
        "Podatke koristimo isključivo za zakonsku prijavu boravka (eVisitor)."
    ),
    "en": (
        "Check-in — documents\n"
        "Please send us photos of ID documents here on WhatsApp before arrival — "
        "one set per adult guest ({adults}): passport (biodata page) or national ID card "
        "(front + back). No flash, full document in frame. "
        "We use this data only for mandatory guest registration (eVisitor)."
    ),
    "de": (
        "Check-in vorbereiten\n"
        "Bitte senden Sie uns vor der Anreise Fotos der Ausweisdokumente hier per WhatsApp — "
        "pro erwachsenem Gast ({adults}): Reisepass (Datenseite) oder Personalausweis "
        "(Vorder- und Rückseite). Ohne Blitz, ganzes Dokument im Bild. "
        "Die Daten verwenden wir ausschließlich für die gesetzliche Meldepflicht (eVisitor)."
    ),
    "es": (
        "Check-in — documentos\n"
        "Por favor, envíenos fotos de los documentos de identidad por WhatsApp antes de la llegada — "
        "un juego por cada huésped adulto ({adults}): pasaporte (página de datos) o DNI "
        "(anverso y reverso). Sin flash, documento completo en la imagen. "
        "Usamos estos datos únicamente para el registro legal de la estancia (eVisitor)."
    ),
    "fr": (
        "Check-in — documents\n"
        "Veuillez nous envoyer par WhatsApp, avant votre arrivée, des photos des pièces d’identité — "
        "un jeu par adulte ({adults}) : passeport (page d’identité) ou carte d’identité "
        "(recto et verso). Sans flash, document entier visible. "
        "Nous utilisons ces données uniquement pour l’enregistrement légal du séjour (eVisitor)."
    ),
}

CHECKIN_READY_BODY = {
    "hr": (
        "Hvala vam na poslanim dokumentima!\n\n"
        "Vaši podaci su spremljeni — kad stignete, check-in će proći brzo i nećete gubiti vrijeme.\n\n"
        "Javite nam, molimo, okvirno vrijeme dolaska."
    ),
    "en": (
        "Thank you for sending your documents!\n\n"
        "Your details are saved — when you arrive, check-in will be quick and you won’t lose time.\n\n"
        "Please let us know your approximate arrival time."
    ),
    "de": (
        "Vielen Dank für die Dokumente!\n\n"
        "Ihre Daten sind registriert — beim Check-in vor Ort geht es schnell, Sie verlieren keine Zeit.\n\n"
        "Bitte teilen Sie uns Ihre ungefähre Ankunftszeit mit."
    ),
    "es": (
        "¡Gracias por enviar los documentos!\n\n"
        "Sus datos están registrados — a su llegada, el check-in será rápido y no perderá tiempo.\n\n"
        "Por favor, indíquenos su hora aproximada de llegada."
    ),
    "fr": (
        "Merci pour l’envoi de vos documents !\n\n"
        "Vos données sont enregistrées — à votre arrivée, l’enregistrement sera rapide.\n\n"
        "Merci de nous indiquer votre heure d’arrivée approximative."
    ),
}

CHECKIN_LINE = {
    "hr": "Check-in: {check_in} od {check_in_time}",
    "en": "Check-in: {check_in} from {check_in_time}",
    "de": "Check-in: {check_in} ab {check_in_time} Uhr",
    "es": "Check-in: {check_in} a partir de las {check_in_time}",
    "fr": "Check-in : {check_in} à partir de {check_in_time}",
}

GREETING = {
    "hr": "Bok {name}!",
    "en": "Hi {name}!",
    "de": "Hallo {name}!",
    "es": "¡Hola {name}!",
    "fr": "Bonjour {name} !",
}

THANKS = {
    "hr": "Hvala na rezervaciji u {property_name}.",
    "en": "Thank you for your booking at {property_name}.",
    "de": "Vielen Dank für Ihre Buchung bei {property_name}.",
    "es": "Gracias por su reserva en {property_name}.",
    "fr": "Merci pour votre réservation chez {property_name}.",
}

RESERVATION_HEADER = {
    "hr": "Vaša rezervacija",
    "en": "Your reservation",
    "de": "Ihre Buchung",
    "es": "Su reserva",
    "fr": "Votre réservation",
}

ROOM_LABEL = {
    "hr": "Soba",
    "en": "Room",
    "de": "Zimmer",
    "es": "Habitación",
    "fr": "Chambre",
}

ADDRESS_LABEL = {
    "hr": "Adresa",
    "en": "Address",
    "de": "Adresse",
    "es": "Dirección",
    "fr": "Adresse",
}

SIGN_OFF = {
    "hr": "Lijep pozdrav,",
    "en": "Best regards,",
    "de": "Mit freundlichen Grüßen,",
    "es": "Un saludo cordial,",
    "fr": "Cordialement,",
}

DEFAULT_GUEST_NAME = {
    "hr": "Gost",
    "en": "Guest",
    "de": "Gast",
    "es": "Huésped",
    "fr": "Client",
}


def _text_for_lang(texts: dict[str, str], lang: str) -> str:
    return texts.get(lang) or texts["en"]


def _normalize_hint(hint: str) -> str:
    return " ".join((hint or "").strip().lower().split())


def _lang_key(reservation: Reservation, override: str | None = None) -> str:
    return compose_language_for_reservation(reservation, override)


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
        "maps_link": MAPS_LINK,
        "notes": (reservation.notes or "").strip(),
        "contact_phone": (contact.get("phone") or "").strip(),
        "message_history": _message_history(reservation),
    }


def _render_checkin_fallback(context: dict) -> str:
    lang = context["language"]
    name = context["guest_name"] or _text_for_lang(DEFAULT_GUEST_NAME, lang)
    adults = context["adults_count"]
    entrance = _text_for_lang(ENTRANCE_TEXTS, lang)
    parking = _text_for_lang(PARKING_TEXTS, lang)
    documents = _text_for_lang(DOCUMENTS_TEXTS, lang).format(adults=adults)
    checkin_line = _text_for_lang(CHECKIN_LINE, lang).format(
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


def _render_checkin_ready_fallback(context: dict) -> str:
    lang = context["language"]
    body = _text_for_lang(CHECKIN_READY_BODY, lang)
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
        return _render_checkin_fallback(context), False, ""

    if intent == GuestMessageIntent.REPLY and _normalize_hint(hint) == HINT_CHECKIN_READY:
        return _render_checkin_ready_fallback(context), False, ""

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
