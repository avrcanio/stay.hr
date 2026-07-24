"""Celery tasks for guest web check-in expiry, reminders, and metrics."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


def _reminder_days_before() -> list[int]:
    raw = getattr(settings, "GUEST_CHECKIN_REMINDER_DAYS_BEFORE", "7,0")
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = str(raw or "").split(",")
    days: list[int] = []
    for item in values:
        item = str(item).strip()
        if not item:
            continue
        try:
            day = int(item)
        except ValueError:
            continue
        if day >= 0 and day not in days:
            days.append(day)
    return days or [7, 0]


@shared_task(name="reservations.expire_guest_checkin_sessions")
def expire_guest_checkin_sessions() -> dict:
    from apps.reservations.guest_checkin_session import expire_stale_sessions

    return expire_stale_sessions()


@shared_task(name="communications.send_pre_arrival_checkin_reminders")
def send_pre_arrival_checkin_reminders() -> dict:
    from apps.communications.guest_reminder_service import GuestReminderService
    from apps.reservations.guest_checkin_analytics import reservations_due_for_checkin_reminder

    if not getattr(settings, "GUEST_CHECKIN_REMINDER_ENABLED", True):
        return {"enabled": False, "sent": 0, "skipped": 0, "already_sent": 0}

    result = {
        "enabled": True,
        "days_before": [],
        "sent": 0,
        "skipped": 0,
        "already_sent": 0,
        "failed": 0,
        "manual_required": 0,
    }

    for days_before in _reminder_days_before():
        result["days_before"].append(days_before)
        reservations = reservations_due_for_checkin_reminder(days_before=days_before)
        for reservation in reservations:
            outcome = GuestReminderService.send_pre_arrival_reminder(
                reservation,
                days_before=days_before,
            )
            status = outcome.get("status")
            if status == "sent" or status == "queued":
                result["sent"] += 1
            elif status == "already_sent":
                result["already_sent"] += 1
            elif status == "manual_required":
                result["manual_required"] += 1
            elif status == "failed":
                result["failed"] += 1
            else:
                result["skipped"] += 1

    logger.info("guest checkin pre_arrival reminders summary=%s", result)
    return result


@shared_task(name="reservations.log_guest_checkin_metrics")
def log_guest_checkin_metrics() -> dict:
    from apps.reservations.guest_checkin_analytics import load_guest_checkin_kpis

    days = max(1, int(getattr(settings, "GUEST_CHECKIN_METRICS_DAYS", 30)))
    kpis = load_guest_checkin_kpis(days=days)
    payload = {
        "lookback_days": kpis.lookback_days,
        "sessions_created": kpis.sessions_created,
        "sessions_ready": kpis.sessions_ready,
        "sessions_completed": kpis.sessions_completed,
        "sessions_expired": kpis.sessions_expired,
        "sessions_revoked": kpis.sessions_revoked,
        "auto_complete_count": kpis.auto_complete_count,
        "ready_to_complete_seconds_median": kpis.ready_to_complete_seconds_median,
        "reminders_sent": kpis.reminders_sent,
    }
    logger.info("guest_checkin metrics snapshot=%s", payload)
    return payload


@shared_task(name="reservations.send_guest_portal_link_after_checkin")
def send_guest_portal_link_after_checkin(reservation_id: int, session_id: int) -> dict:
    """After web check-in complete: ensure portal access and send link on the same channel."""
    from apps.communications.guest_portal_distribute import send_guest_portal_link_for_session

    return send_guest_portal_link_for_session(
        reservation_id=reservation_id,
        session_id=session_id,
    )