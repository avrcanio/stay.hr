"""Schedule and handle auto check-in document deadline (check_in_time + 30 min)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone

from apps.communications.guest_compose import (
    HINT_AUTO_CHECKIN_DOCS_EXPIRED,
    HINT_AUTO_CHECKIN_PERIOD_ENDED,
    render_autocheckin_expired_short_message,
    render_autocheckin_period_ended_message,
)
from apps.communications.models import GuestMessageDraft
from apps.core.timezone import property_local_now
from apps.integrations.whatsapp.apply_reply import (
    is_document_checkin_complete,
    is_whatsapp_autocheckin_waived,
    waive_whatsapp_autocheckin,
)
from apps.integrations.whatsapp.evisitor_reply import _send_reservation_whatsapp_text
from apps.integrations.whatsapp.guest_docs_awaiting_arrival import (
    docs_awaiting_arrival_already_sent,
    notify_guest_docs_awaiting_arrival,
)
from apps.properties.models import Property
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)

DOCS_DEADLINE_AFTER_CHECKIN = timedelta(minutes=30)
SESSION_LOST_WINDOW = timedelta(minutes=15)


def autocheckin_docs_deadline_at(reservation: Reservation) -> datetime:
    prop = reservation.property
    now = property_local_now(prop)
    tz = now.tzinfo
    checkin_dt = datetime.combine(reservation.check_in, prop.check_in_time, tzinfo=tz)
    return checkin_dt + DOCS_DEADLINE_AFTER_CHECKIN


def _docs_expired_already_handled(reservation: Reservation) -> bool:
    return GuestMessageDraft.objects.filter(
        reservation=reservation,
        hint=HINT_AUTO_CHECKIN_DOCS_EXPIRED,
    ).exists()


def _period_ended_sent_today(reservation: Reservation) -> bool:
    now = property_local_now(reservation.property)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return GuestMessageDraft.objects.filter(
        reservation=reservation,
        hint=HINT_AUTO_CHECKIN_PERIOD_ENDED,
        sent_at__gte=start_of_day,
    ).exists()


def is_before_property_check_in_time(reservation: Reservation) -> bool:
    prop = reservation.property
    now = property_local_now(prop)
    if reservation.check_in != now.date():
        return False
    return now.time() < prop.check_in_time


def maybe_reply_autocheckin_period_ended_inbound(
    *,
    reservation: Reservation,
    action_text: str,
) -> dict | None:
    """Before check_in_time: engaged guest without docs gets a short period-ended reply."""
    if not (action_text or "").strip():
        return None
    if is_whatsapp_autocheckin_waived(reservation):
        return None
    if is_document_checkin_complete(reservation):
        return None
    if reservation.whatsapp_autocheckin_engaged_at is None:
        return None
    if not is_before_property_check_in_time(reservation):
        return None
    if _period_ended_sent_today(reservation):
        return None

    body = render_autocheckin_period_ended_message(reservation)
    return _send_reservation_whatsapp_text(
        reservation=reservation,
        body=body,
        hint=HINT_AUTO_CHECKIN_PERIOD_ENDED,
    )


def schedule_autocheckin_docs_deadline(reservation: Reservation) -> dict:
    """Queue Celery task at check_in_time + 30 min on check-in day."""
    if reservation.status != Reservation.Status.EXPECTED:
        return {"status": "skipped", "reason": "not_expected"}
    if is_whatsapp_autocheckin_waived(reservation):
        return {"status": "skipped", "reason": "waived"}
    if is_document_checkin_complete(reservation):
        return {"status": "skipped", "reason": "docs_complete"}
    if reservation.whatsapp_autocheckin_engaged_at is None:
        return {"status": "skipped", "reason": "not_engaged"}

    prop = reservation.property
    now = property_local_now(prop)
    if reservation.check_in != now.date():
        return {"status": "skipped", "reason": "not_checkin_day"}

    if reservation.whatsapp_autocheckin_docs_deadline_at is not None:
        return {"status": "skipped", "reason": "already_scheduled"}

    run_at = autocheckin_docs_deadline_at(reservation)
    if run_at <= now:
        return autocheckin_docs_deadline_elapsed(reservation.pk)

    reservation.whatsapp_autocheckin_docs_deadline_at = run_at
    reservation.save(update_fields=["whatsapp_autocheckin_docs_deadline_at", "updated_at"])

    task_id = f"autocheckin-docs-deadline-{reservation.pk}-{reservation.check_in.isoformat()}"
    autocheckin_docs_deadline_elapsed.apply_async(
        args=[reservation.pk],
        eta=run_at,
        task_id=task_id,
    )
    return {"status": "scheduled", "run_at": run_at.isoformat(), "task_id": task_id}


@shared_task
def autocheckin_docs_deadline_elapsed(reservation_id: int) -> dict:
    reservation = (
        Reservation.objects.select_related("property", "tenant")
        .filter(pk=reservation_id)
        .first()
    )
    if reservation is None:
        return {"status": "missing"}

    if reservation.status != Reservation.Status.EXPECTED:
        return {"status": "skipped", "reason": "not_expected"}
    if is_document_checkin_complete(reservation):
        return {"status": "skipped", "reason": "docs_complete"}
    if is_whatsapp_autocheckin_waived(reservation):
        return {"status": "skipped", "reason": "waived"}
    if reservation.whatsapp_autocheckin_engaged_at is None:
        return {"status": "skipped", "reason": "not_engaged"}
    if _docs_expired_already_handled(reservation):
        return {"status": "skipped", "reason": "already_handled"}

    waive_whatsapp_autocheckin(reservation)
    reservation.refresh_from_db()

    expired_body = render_autocheckin_expired_short_message(reservation)
    expired_result = _send_reservation_whatsapp_text(
        reservation=reservation,
        body=expired_body,
        hint=HINT_AUTO_CHECKIN_DOCS_EXPIRED,
    )

    welcome_result: dict = {"status": "skipped", "reason": "already_sent"}
    if not docs_awaiting_arrival_already_sent(reservation):
        welcome_result = notify_guest_docs_awaiting_arrival(reservation)

    logger.info(
        "autocheckin docs deadline elapsed reservation_id=%s expired=%s welcome=%s",
        reservation.pk,
        expired_result.get("status"),
        welcome_result.get("status"),
    )
    return {
        "status": "handled",
        "expired": expired_result,
        "welcome": welcome_result,
    }


def mark_autocheckin_session_lost_for_due_reservations() -> dict:
    """At check_in_time - 1h: flag welcome-sent reservations with no guest engagement."""
    marked = 0
    for prop in Property.objects.filter(whatsapp_autocheckin_enabled=True).select_related("tenant"):
        now = property_local_now(prop)
        session_cutoff = datetime.combine(
            now.date(),
            prop.check_in_time,
            tzinfo=now.tzinfo,
        ) - timedelta(hours=1)
        if not (session_cutoff <= now < session_cutoff + SESSION_LOST_WINDOW):
            continue

        qs = Reservation.objects.filter(
            tenant_id=prop.tenant_id,
            property=prop,
            check_in=now.date(),
            status=Reservation.Status.EXPECTED,
            whatsapp_welcome_sent_at__isnull=False,
            whatsapp_autocheckin_engaged_at__isnull=True,
            whatsapp_autocheckin_session_lost=False,
        )
        for reservation in qs:
            reservation.whatsapp_autocheckin_session_lost = True
            reservation.save(update_fields=["whatsapp_autocheckin_session_lost", "updated_at"])
            marked += 1
            logger.info(
                "autocheckin session lost (no engagement before T-1h) reservation_id=%s",
                reservation.pk,
            )

    return {"marked": marked}


@shared_task
def run_autocheckin_session_lost_scan() -> dict:
    return mark_autocheckin_session_lost_for_due_reservations()
