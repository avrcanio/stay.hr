from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.utils import timezone

from apps.communications.guest_compose import compose_language_for_reservation
from apps.core.timezone import property_local_now
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.client import (
    WhatsAppApiError,
    extract_outbound_wamid,
    send_interactive_button_message,
    send_text_message,
)
from apps.integrations.whatsapp.reservation_lookup import (
    ACTIVE_STATUSES,
    find_reservation_for_wa_id,
)
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.reservations.models import (
    Reservation,
    WhatsAppGuestAutocheckinSession,
    WhatsAppGuestAutocheckinSessionStatus,
)

logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(hours=24)
GUEST_AUTO_CHECKIN_BUTTON_ID = "guest_auto_checkin"

_GUEST_AUTO_CHECKIN_BUTTON_TITLE = {
    "hr": "Auto check-in",
    "en": "Auto check-in",
    "de": "Autocheck-in",
    "es": "Auto check-in",
    "fr": "Auto check-in",
}

_ASK_BOOKING_CODE = {
    "hr": (
        "Bok! Ne mogu pronaći rezervaciju za ovaj broj.\n\n"
        "Molimo pošaljite booking kod (npr. s Booking.com potvrde)."
    ),
    "en": (
        "Hi! I could not find a reservation for this number.\n\n"
        "Please send your booking code (e.g. from your Booking.com confirmation)."
    ),
    "de": (
        "Guten Tag! Für diese Nummer habe ich keine Reservierung gefunden.\n\n"
        "Bitte senden Sie Ihre Buchungsnummer (z. B. aus der Booking.com-Bestätigung)."
    ),
    "es": (
        "¡Hola! No encontramos una reserva para este número.\n\n"
        "Envíe su código de reserva (p. ej. de la confirmación de Booking.com)."
    ),
    "fr": (
        "Bonjour ! Aucune réservation trouvée pour ce numéro.\n\n"
        "Veuillez envoyer votre code de réservation (ex. confirmation Booking.com)."
    ),
}

_AUTOCHECKIN_GREETING = {
    "hr": (
        "Bok {name}! Vidim rezervaciju {booking_code} "
        "({check_in}–{check_out}) u {property_name}.\n\n"
        "Pritisnite Auto check-in za brzi online check-in."
    ),
    "en": (
        "Hi {name}! I see booking {booking_code} "
        "({check_in}–{check_out}) at {property_name}.\n\n"
        "Tap Auto check-in for quick online check-in."
    ),
    "de": (
        "Guten Tag {name}! Ich sehe Buchung {booking_code} "
        "({check_in}–{check_out}) in {property_name}.\n\n"
        "Tippen Sie auf Autocheck-in für den Online-Check-in."
    ),
    "es": (
        "¡Hola {name}! Veo la reserva {booking_code} "
        "({check_in}–{check_out}) en {property_name}.\n\n"
        "Pulse Auto check-in para el check-in online."
    ),
    "fr": (
        "Bonjour {name} ! Je vois la réservation {booking_code} "
        "({check_in}–{check_out}) à {property_name}.\n\n"
        "Appuyez sur Auto check-in pour l’enregistrement en ligne."
    ),
}


def is_guest_auto_checkin_button(*, button_id: str = "", text: str = "") -> bool:
    if (button_id or "").strip() == GUEST_AUTO_CHECKIN_BUTTON_ID:
        return True
    from apps.integrations.whatsapp.tasks import is_auto_checkin_quick_reply

    return is_auto_checkin_quick_reply(text)


def extract_booking_code_from_text(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"[A-Za-z0-9\-]{4,64}", raw) and not raw.isdigit():
        return raw
    matches = re.findall(r"\b(\d{6,12})\b", raw)
    if not matches:
        return None
    return matches[0]


def find_reservation_by_booking_code(*, tenant_id: int, code: str) -> Reservation | None:
    code = (code or "").strip()
    if not code:
        return None
    qs = Reservation.objects.filter(
        tenant_id=tenant_id,
        status__in=ACTIVE_STATUSES,
        booking_code__iexact=code,
    ).select_related("property", "tenant")
    if not qs.exists():
        qs = Reservation.objects.filter(
            tenant_id=tenant_id,
            status__in=ACTIVE_STATUSES,
            external_id__iexact=code,
        ).select_related("property", "tenant")
    candidates = list(qs)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    today = timezone.localdate()
    return min(candidates, key=lambda row: abs((row.check_in - today).days))


def _text_for_lang(texts: dict[str, str], lang: str) -> str:
    base = (lang or "en").split("-")[0].lower()
    return texts.get(base) or texts.get("en") or next(iter(texts.values()))


def _button_title(lang: str) -> str:
    return _text_for_lang(_GUEST_AUTO_CHECKIN_BUTTON_TITLE, lang)


def _session_expired(session: WhatsAppGuestAutocheckinSession) -> bool:
    return session.last_activity_at + SESSION_TTL < timezone.now()


def _get_awaiting_session(*, tenant_id: int, wa_id: str) -> WhatsAppGuestAutocheckinSession | None:
    session = (
        WhatsAppGuestAutocheckinSession.objects.filter(
            tenant_id=tenant_id,
            wa_id=wa_id,
            status=WhatsAppGuestAutocheckinSessionStatus.AWAITING_BOOKING_CODE,
        )
        .order_by("-last_activity_at", "id")
        .first()
    )
    if session is None:
        return None
    if _session_expired(session):
        session.delete()
        return None
    return session


def _clear_session(*, tenant_id: int, wa_id: str) -> None:
    WhatsAppGuestAutocheckinSession.objects.filter(
        tenant_id=tenant_id,
        wa_id=wa_id,
    ).delete()


def _ensure_awaiting_session(*, tenant_id: int, wa_id: str) -> WhatsAppGuestAutocheckinSession:
    session = _get_awaiting_session(tenant_id=tenant_id, wa_id=wa_id)
    if session is not None:
        session.last_activity_at = timezone.now()
        session.save(update_fields=["last_activity_at", "updated_at"])
        return session
    return WhatsAppGuestAutocheckinSession.objects.create(
        tenant_id=tenant_id,
        wa_id=wa_id,
        status=WhatsAppGuestAutocheckinSessionStatus.AWAITING_BOOKING_CODE,
    )


def _link_message_to_reservation(row: WhatsAppMessage, reservation: Reservation) -> None:
    if row.reservation_id == reservation.pk:
        return
    row.reservation = reservation
    row.save(update_fields=["reservation"])


def _send_whatsapp_text(
    *,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    row: WhatsAppMessage,
    reservation: Reservation | None,
    body: str,
) -> dict:
    try:
        response = send_text_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=row.wa_id,
            body=body,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        logger.warning("Guest autocheckin text failed message_id=%s: %s", row.pk, exc)
        return {"status": "send_failed", "detail": str(exc)}

    outbound_wamid = extract_outbound_wamid(response)
    if outbound_wamid:
        WhatsAppMessage.objects.create(
            tenant_id=integration_row.tenant_id,
            integration=integration_row,
            reservation=reservation,
            wamid=outbound_wamid,
            wa_id=row.wa_id,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="text",
            body=body,
            raw_payload=response,
        )
    return {"status": "sent", "outbound_wamid": outbound_wamid}


def _send_autocheckin_prompt(
    *,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    row: WhatsAppMessage,
    reservation: Reservation,
) -> dict:
    lang = compose_language_for_reservation(reservation)
    name = (reservation.booker_name or "").strip() or ("gost" if lang == "hr" else "guest")
    body = _text_for_lang(_AUTOCHECKIN_GREETING, lang).format(
        name=name.split()[0] if name else name,
        booking_code=reservation.booking_code or reservation.external_id or str(reservation.pk),
        check_in=reservation.check_in.strftime("%d.%m.%Y" if lang == "hr" else "%Y-%m-%d"),
        check_out=reservation.check_out.strftime("%d.%m.%Y" if lang == "hr" else "%Y-%m-%d"),
        property_name=reservation.property.name,
    )
    try:
        response = send_interactive_button_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=row.wa_id,
            body=body,
            buttons=[(GUEST_AUTO_CHECKIN_BUTTON_ID, _button_title(lang))],
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        logger.warning("Guest autocheckin prompt failed message_id=%s: %s", row.pk, exc)
        return {"status": "send_failed", "detail": str(exc)}

    outbound_wamid = extract_outbound_wamid(response)
    if outbound_wamid:
        WhatsAppMessage.objects.create(
            tenant_id=integration_row.tenant_id,
            integration=integration_row,
            reservation=reservation,
            wamid=outbound_wamid,
            wa_id=row.wa_id,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="interactive",
            body=body,
            raw_payload=response,
        )
    return {"status": "autocheckin_prompt_sent", "outbound_wamid": outbound_wamid}


def _is_autocheckin_day(reservation: Reservation) -> bool:
    prop = reservation.property
    if not prop.whatsapp_autocheckin_enabled:
        return False
    now = property_local_now(prop)
    return reservation.check_in == now.date()


def resolve_guest_reservation(
    *,
    row: WhatsAppMessage,
    action_text: str,
) -> Reservation | None:
    if row.reservation_id is not None:
        return row.reservation

    reservation = find_reservation_for_wa_id(tenant_id=row.tenant_id, wa_id=row.wa_id)
    if reservation is not None:
        _link_message_to_reservation(row, reservation)
        _clear_session(tenant_id=row.tenant_id, wa_id=row.wa_id)
        return reservation

    session = _get_awaiting_session(tenant_id=row.tenant_id, wa_id=row.wa_id)
    code = extract_booking_code_from_text(action_text)
    if code is None and session is not None:
        stripped = action_text.strip()
        code = extract_booking_code_from_text(stripped) or stripped or None

    if code:
        reservation = find_reservation_by_booking_code(tenant_id=row.tenant_id, code=code)
        if reservation is not None:
            _link_message_to_reservation(row, reservation)
            _clear_session(tenant_id=row.tenant_id, wa_id=row.wa_id)
            return reservation

    return None


def handle_guest_autocheckin_inbound(
    *,
    row: WhatsAppMessage,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    action_text: str,
    reservation: Reservation | None,
) -> dict:
    from apps.communications.whatsapp_autocheckin_tasks import mark_autocheckin_engaged
    from apps.integrations.whatsapp.reply import build_greeting

    resolved = reservation or resolve_guest_reservation(row=row, action_text=action_text)
    if resolved is not None:
        mark_autocheckin_engaged(resolved)
        if _is_autocheckin_day(resolved):
            return _send_autocheckin_prompt(
                integration_row=integration_row,
                runtime=runtime,
                row=row,
                reservation=resolved,
            )
        body = build_greeting(
            integration_row=integration_row,
            reservation=resolved,
            profile_name="",
        )
        return _send_whatsapp_text(
            integration_row=integration_row,
            runtime=runtime,
            row=row,
            reservation=resolved,
            body=body,
        )

    _ensure_awaiting_session(tenant_id=row.tenant_id, wa_id=row.wa_id)
    lang = (integration_row.tenant.default_language or "hr").split("-")[0].lower()
    body = _text_for_lang(_ASK_BOOKING_CODE, lang)
    return _send_whatsapp_text(
        integration_row=integration_row,
        runtime=runtime,
        row=row,
        reservation=None,
        body=body,
    )
