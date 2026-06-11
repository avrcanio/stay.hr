"""Toni arrival gate: operator prompts, guest timers, Da/Ne/time handler."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

from apps.communications.message_threads_service import _room_name_for_reservation
from apps.core.timezone import property_local_now
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.arrival_time_parse import (
    _property_tz,
    format_guest_stated_arrival_for_operator,
    parse_guest_stated_arrival,
    parse_operator_confirmed_arrival_time,
)
from apps.integrations.whatsapp.client import WhatsAppApiError, extract_outbound_wamid, send_interactive_button_message
from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.integrations.whatsapp.whatsapp_operator import operator_name_for_wa_id, operator_phones_for_tenant
from apps.integrations.whatsapp.whatsapp_post_checkin_reply import (
    guest_message_mentions_arrival,
    send_arrival_thanks_only,
)
from apps.properties.models import Property
from apps.reservations.models import (
    Reservation,
    WhatsAppArrivalConfirmSession,
    WhatsAppArrivalConfirmSessionStatus,
    WhatsAppArrivalConfirmTrigger,
)

logger = logging.getLogger(__name__)

OPERATOR_ARRIVED_YES_PREFIX = "op_arrived_yes"
OPERATOR_ARRIVED_NO_PREFIX = "op_arrived_no"
OPERATOR_ARRIVED_YES_LABEL = "Da"
OPERATOR_ARRIVED_NO_LABEL = "Ne"

_TIMER_CACHE_PREFIX = "wa-arrival-timer"
_TIMER_CACHE_TTL = 86400

_ACTIVE_SESSION_STATUSES = frozenset(
    {
        WhatsAppArrivalConfirmSessionStatus.AWAITING_ARRIVED,
        WhatsAppArrivalConfirmSessionStatus.AWAITING_TIME,
    }
)


def operator_arrived_yes_button_id(reservation_id: int) -> str:
    return f"{OPERATOR_ARRIVED_YES_PREFIX}_{reservation_id}"


def operator_arrived_no_button_id(reservation_id: int) -> str:
    return f"{OPERATOR_ARRIVED_NO_PREFIX}_{reservation_id}"


def parse_operator_arrived_button(button_id: str) -> tuple[str | None, int | None]:
    raw = (button_id or "").strip()
    for prefix, answer in (
        (OPERATOR_ARRIVED_YES_PREFIX, "yes"),
        (OPERATOR_ARRIVED_NO_PREFIX, "no"),
    ):
        if raw == prefix:
            return answer, None
        if raw.startswith(f"{prefix}_"):
            suffix = raw[len(prefix) + 1 :]
            if suffix.isdigit():
                return answer, int(suffix)
    return None, None


def is_operator_arrived_yes_reply(*, button_id: str = "", text: str = "") -> bool:
    answer, _ = parse_operator_arrived_button(button_id)
    if answer == "yes":
        return True
    return (text or "").strip().lower() in {"da", "yes", "ja"}


def is_operator_arrived_no_reply(*, button_id: str = "", text: str = "") -> bool:
    answer, _ = parse_operator_arrived_button(button_id)
    if answer == "no":
        return True
    return (text or "").strip().lower() in {"ne", "no", "nein"}


def _timer_cache_key(reservation_id: int) -> str:
    return f"{_TIMER_CACHE_PREFIX}:{reservation_id}"


def _revoke_scheduled_timer(reservation_id: int) -> None:
    from config.celery import app

    cache_key = _timer_cache_key(reservation_id)
    task_id = cache.get(cache_key)
    if not task_id:
        return
    app.control.revoke(task_id, terminate=False)
    cache.delete(cache_key)


def _pg_advisory_xact_lock_reservation(reservation_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [reservation_id & 0x7FFFFFFF])


def _start_of_property_day(reservation: Reservation):
    now = property_local_now(reservation.property)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _should_skip_arrival_prompt(reservation: Reservation) -> str | None:
    from apps.integrations.whatsapp.apply_reply import is_whatsapp_autocheckin_waived

    if reservation.status in {
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CANCELED,
    }:
        return reservation.status
    if is_whatsapp_autocheckin_waived(reservation):
        return "waived"
    return None


def _awaiting_arrived_prompt_exists_today(
    reservation: Reservation,
    trigger: str,
) -> bool:
    start = _start_of_property_day(reservation)
    return WhatsAppArrivalConfirmSession.objects.filter(
        reservation=reservation,
        trigger=trigger,
        prompted_at__gte=start,
        status=WhatsAppArrivalConfirmSessionStatus.AWAITING_ARRIVED,
    ).exists()


def _build_arrival_confirm_prompt_body(reservation: Reservation) -> str:
    room = _room_name_for_reservation(reservation) or "—"
    code = reservation.booking_code or reservation.external_id or str(reservation.pk)
    guest_plan = format_guest_stated_arrival_for_operator(reservation)
    lines = [
        f"#{reservation.pk} · soba {room} · {reservation.booker_name} · {code}",
    ]
    if guest_plan:
        lines.append(f"Gost javio: {guest_plan}")
    lines.append("Došli svi gosti?")
    return "\n".join(lines)


def send_arrival_confirm_prompt(
    reservation: Reservation,
    *,
    trigger: str,
    integration_row: IntegrationConfig | None = None,
    runtime: WhatsAppRuntimeConfig | None = None,
) -> dict:
    reservation = Reservation.objects.select_related("property", "tenant").get(pk=reservation.pk)
    skip = _should_skip_arrival_prompt(reservation)
    if skip:
        return {"status": "skipped", "reason": skip}

    if _awaiting_arrived_prompt_exists_today(reservation, trigger):
        return {"status": "skipped", "reason": "already_prompted"}

    if integration_row is None or runtime is None:
        integration_row, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration_row is None or runtime is None:
        return {"status": "skipped", "reason": "no_integration"}

    operators = operator_phones_for_tenant(reservation.tenant_id)
    if not operators:
        return {"status": "skipped", "reason": "no_operators"}

    body = _build_arrival_confirm_prompt_body(reservation)
    yes_id = operator_arrived_yes_button_id(reservation.pk)
    no_id = operator_arrived_no_button_id(reservation.pk)
    send_results: list[dict] = []

    from apps.integrations.whatsapp.phone import normalize_phone

    for operator in operators:
        operator_wa_id = normalize_phone(operator["phone"])
        if not operator_wa_id:
            continue
        try:
            response = send_interactive_button_message(
                phone_number_id=runtime.phone_number_id,
                access_token=runtime.access_token,
                to_wa_id=operator_wa_id,
                body=body,
                buttons=[
                    (yes_id, OPERATOR_ARRIVED_YES_LABEL),
                    (no_id, OPERATOR_ARRIVED_NO_LABEL),
                ],
                provider=runtime.provider,
                api_base_url=runtime.api_base_url,
            )
        except WhatsAppApiError as exc:
            logger.warning(
                "Arrival confirm prompt failed reservation_id=%s wa_id=%s: %s",
                reservation.pk,
                operator_wa_id,
                exc,
            )
            send_results.append({"wa_id": operator_wa_id, "status": "send_failed", "detail": str(exc)})
            continue

        outbound_wamid = extract_outbound_wamid(response)
        if outbound_wamid:
            WhatsAppMessage.objects.create(
                tenant_id=reservation.tenant_id,
                integration=integration_row,
                reservation=reservation,
                wamid=outbound_wamid,
                wa_id=operator_wa_id,
                phone_number_id=runtime.phone_number_id,
                direction=WhatsAppMessage.Direction.OUTBOUND,
                message_type="interactive",
                body=body,
                raw_payload=response,
            )
        send_results.append({"wa_id": operator_wa_id, "status": "sent", "outbound_wamid": outbound_wamid})

    if not any(item.get("status") == "sent" for item in send_results):
        return {"status": "send_failed", "operators": send_results}

    now = timezone.now()
    session = (
        WhatsAppArrivalConfirmSession.objects.filter(
            reservation=reservation,
            status__in=_ACTIVE_SESSION_STATUSES,
        )
        .order_by("-id")
        .first()
    )
    if session is None:
        session = WhatsAppArrivalConfirmSession.objects.create(
            tenant_id=reservation.tenant_id,
            reservation=reservation,
            status=WhatsAppArrivalConfirmSessionStatus.AWAITING_ARRIVED,
            trigger=trigger,
            guest_stated_arrival_text=reservation.guest_stated_arrival_text,
            guest_stated_arrival_at=reservation.guest_stated_arrival_at,
            prompted_at=now,
        )
    else:
        session.status = WhatsAppArrivalConfirmSessionStatus.AWAITING_ARRIVED
        session.trigger = trigger
        session.prompted_at = now
        session.responded_operator_wa_id = ""
        session.confirmed_arrival_at = None
        session.guest_stated_arrival_text = reservation.guest_stated_arrival_text
        session.guest_stated_arrival_at = reservation.guest_stated_arrival_at
        session.save(
            update_fields=[
                "status",
                "trigger",
                "prompted_at",
                "responded_operator_wa_id",
                "confirmed_arrival_at",
                "guest_stated_arrival_text",
                "guest_stated_arrival_at",
                "updated_at",
            ]
        )

    return {"status": "prompted", "session_id": session.pk, "operators": send_results}


def schedule_arrival_confirm_prompt(
    reservation: Reservation,
    *,
    trigger: str = WhatsAppArrivalConfirmTrigger.GUEST_DEADLINE_PLUS_30,
    run_at=None,
) -> dict:
    """Schedule Celery task for Toni prompt; revokes any prior timer for this reservation."""
    _revoke_scheduled_timer(reservation.pk)
    now = property_local_now(reservation.property)
    if run_at is None:
        countdown = 0
    else:
        countdown = max(0, int((run_at - now).total_seconds()))

    from config.celery import app

    task_id = f"wa-arrival-{reservation.pk}-{uuid.uuid4().hex[:12]}"
    cache.set(_timer_cache_key(reservation.pk), task_id, timeout=_TIMER_CACHE_TTL)
    arrival_confirm_guest_deadline_elapsed.apply_async(
        args=[reservation.pk, trigger],
        countdown=countdown,
        task_id=task_id,
    )
    return {"status": "scheduled", "countdown": countdown, "task_id": task_id}


def save_guest_stated_arrival(reservation: Reservation, *, text: str) -> datetime | None:
    parsed = parse_guest_stated_arrival(text, reservation)
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


def maybe_handle_guest_arrival_time_inbound(
    *,
    row: WhatsAppMessage,
    reservation: Reservation,
    action_text: str,
) -> dict | None:
    from apps.integrations.whatsapp.apply_reply import is_document_checkin_complete

    if reservation.status != Reservation.Status.EXPECTED:
        return None
    if not is_document_checkin_complete(reservation):
        return None
    if not guest_message_mentions_arrival(action_text):
        return None

    parsed = save_guest_stated_arrival(reservation, text=action_text)
    thanks = send_arrival_thanks_only(row=row, reservation=reservation)
    schedule_result = {"status": "skipped", "reason": "no_parsed_time"}
    if parsed is not None:
        run_at = parsed + timedelta(minutes=30)
        schedule_result = schedule_arrival_confirm_prompt(
            reservation,
            trigger=WhatsAppArrivalConfirmTrigger.GUEST_DEADLINE_PLUS_30,
            run_at=run_at,
        )
    return {
        "status": "guest_arrival_saved",
        "thanks": thanks,
        "parsed_at": parsed.isoformat() if parsed else None,
        "schedule": schedule_result,
    }


@shared_task
def arrival_confirm_guest_deadline_elapsed(
    reservation_id: int,
    trigger: str = WhatsAppArrivalConfirmTrigger.GUEST_DEADLINE_PLUS_30,
) -> dict:
    reservation = (
        Reservation.objects.select_related("property", "tenant")
        .filter(pk=reservation_id)
        .first()
    )
    if reservation is None:
        return {"status": "missing"}
    return send_arrival_confirm_prompt(reservation, trigger=trigger)


@shared_task
def send_nightly_arrival_confirm_prompts() -> dict:
    from apps.integrations.whatsapp.apply_reply import (
        is_document_checkin_complete,
        is_whatsapp_autocheckin_waived,
    )

    result = {"prompted": 0, "skipped": 0, "failed": 0}
    props = Property.objects.filter(whatsapp_autocheckin_enabled=True).select_related("tenant")
    for prop in props:
        now = property_local_now(prop)
        if not (23 <= now.hour <= 23 and now.minute < 15):
            continue
        target_date = now.date()
        qs = Reservation.objects.filter(
            tenant_id=prop.tenant_id,
            property=prop,
            check_in=target_date,
            status=Reservation.Status.EXPECTED,
        ).select_related("property", "tenant")
        for reservation in qs:
            if is_whatsapp_autocheckin_waived(reservation):
                result["skipped"] += 1
                continue
            if not is_document_checkin_complete(reservation):
                result["skipped"] += 1
                continue
            outcome = send_arrival_confirm_prompt(
                reservation,
                trigger=WhatsAppArrivalConfirmTrigger.NIGHTLY_23H,
            )
            status = outcome.get("status")
            if status == "prompted":
                result["prompted"] += 1
            elif status == "send_failed":
                result["failed"] += 1
            else:
                result["skipped"] += 1
    return result


def _get_session_for_operator_response(
    *,
    tenant_id: int,
    reservation_id: int | None,
    operator_wa_id: str,
    status: str,
) -> WhatsAppArrivalConfirmSession | None:
    qs = WhatsAppArrivalConfirmSession.objects.select_related(
        "reservation",
        "reservation__property",
        "reservation__tenant",
    ).filter(
        tenant_id=tenant_id,
        status=status,
    )
    if reservation_id is not None:
        qs = qs.filter(reservation_id=reservation_id)
    if status == WhatsAppArrivalConfirmSessionStatus.AWAITING_TIME:
        qs = qs.filter(responded_operator_wa_id=operator_wa_id)
    return qs.order_by("-prompted_at", "-id").first()


def _already_handled_message(reservation: Reservation) -> str:
    return f"Već obrađeno za #{reservation.pk}."


def handle_operator_arrival_confirm_inbound(
    *,
    row: WhatsAppMessage,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    action_text: str,
    button_id: str = "",
) -> dict | None:
    from apps.integrations.whatsapp.whatsapp_operator_service import _send_operator_text
    from apps.reservations.reservation_checkin_complete import perform_arrival_confirmed_checkin

    answer, reservation_id = parse_operator_arrived_button(button_id)

    if answer in {"yes", "no"} and reservation_id is not None:
        with transaction.atomic():
            _pg_advisory_xact_lock_reservation(reservation_id)
            session = _get_session_for_operator_response(
                tenant_id=row.tenant_id,
                reservation_id=reservation_id,
                operator_wa_id=row.wa_id,
                status=WhatsAppArrivalConfirmSessionStatus.AWAITING_ARRIVED,
            )
            if session is None:
                reservation = Reservation.objects.filter(pk=reservation_id).first()
                if reservation is not None:
                    _send_operator_text(
                        integration_row=integration_row,
                        runtime=runtime,
                        operator_wa_id=row.wa_id,
                        body=_already_handled_message(reservation),
                        reservation=reservation,
                    )
                return {"status": "already_handled", "reservation_id": reservation_id}

            reservation = session.reservation
            if answer == "no":
                session.status = WhatsAppArrivalConfirmSessionStatus.DECLINED
                session.responded_operator_wa_id = row.wa_id
                session.save(update_fields=["status", "responded_operator_wa_id", "updated_at"])
                _send_operator_text(
                    integration_row=integration_row,
                    runtime=runtime,
                    operator_wa_id=row.wa_id,
                    body="OK, bez check-ina.",
                    reservation=reservation,
                )
                return {"status": "declined", "session_id": session.pk}

            session.status = WhatsAppArrivalConfirmSessionStatus.AWAITING_TIME
            session.responded_operator_wa_id = row.wa_id
            session.save(update_fields=["status", "responded_operator_wa_id", "updated_at"])
            guest_plan = format_guest_stated_arrival_for_operator(reservation)
            prompt = "U koliko sati su došli? (npr. 19:30)"
            if guest_plan:
                prompt = f"{prompt}\n(Gost je javio: {guest_plan})"
            _send_operator_text(
                integration_row=integration_row,
                runtime=runtime,
                operator_wa_id=row.wa_id,
                body=prompt,
                reservation=reservation,
            )
            return {"status": "awaiting_time", "session_id": session.pk}

    session = _get_session_for_operator_response(
        tenant_id=row.tenant_id,
        reservation_id=None,
        operator_wa_id=row.wa_id,
        status=WhatsAppArrivalConfirmSessionStatus.AWAITING_TIME,
    )
    if session is None:
        return None

    parsed = parse_operator_confirmed_arrival_time(action_text, session.reservation)
    if parsed is None:
        _send_operator_text(
            integration_row=integration_row,
            runtime=runtime,
            operator_wa_id=row.wa_id,
            body="Nisam razumio vrijeme. Molim format HH:MM (npr. 19:30).",
            reservation=session.reservation,
        )
        return {"status": "time_parse_failed", "session_id": session.pk}

    with transaction.atomic():
        _pg_advisory_xact_lock_reservation(session.reservation_id)
        session.refresh_from_db()
        if session.status != WhatsAppArrivalConfirmSessionStatus.AWAITING_TIME:
            _send_operator_text(
                integration_row=integration_row,
                runtime=runtime,
                operator_wa_id=row.wa_id,
                body=_already_handled_message(session.reservation),
                reservation=session.reservation,
            )
            return {"status": "already_handled", "session_id": session.pk}

        time_stay_from = parsed.astimezone(_property_tz(session.reservation)).strftime("%H:%M")
        outcome = perform_arrival_confirmed_checkin(
            session.reservation,
            time_stay_from=time_stay_from,
            operator_wa_id=row.wa_id,
            confirmed_arrival_at=parsed,
            integration_row=integration_row,
            runtime=runtime,
        )
        if outcome.get("status") == "completed":
            session.status = WhatsAppArrivalConfirmSessionStatus.DONE
            session.confirmed_arrival_at = parsed
            session.save(update_fields=["status", "confirmed_arrival_at", "updated_at"])
        return outcome
