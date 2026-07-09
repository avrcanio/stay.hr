"""Guest web check-in analytics KPIs and structured metric logging."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median

from django.db.models import Count, Q
from django.utils import timezone

from apps.communications.guest_compose import HINT_GUEST_WEB_CHECKIN_REMINDER
from apps.communications.models import GuestMessageDraft
from apps.properties.models import Property
from apps.reservations.checkin_readiness import effective_session_status
from apps.reservations.guest_checkin_progress import checkin_progress_for_reservation
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    GuestCheckInSession,
    GuestCheckInSessionStatus,
    Reservation,
)
from apps.tenants.models import Tenant


@dataclass(frozen=True)
class GuestCheckInKPIs:
    lookback_days: int
    sessions_created: int
    sessions_active: int = 0
    sessions_ready_not_completed: int = 0
    sessions_ready: int = 0
    sessions_completed: int = 0
    sessions_expired: int = 0
    sessions_revoked: int = 0
    auto_complete_count: int = 0
    completion_rate: float | None = None
    created_to_ready_seconds_median: float | None = None
    ready_to_complete_seconds_median: float | None = None
    reminders_sent: int = 0
    reminders_by_channel: dict[str, dict[str, int]] = field(default_factory=dict)
    ocr_jobs_applied: int = 0
    completed_with_ocr: int = 0
    completed_manual_only: int = 0


logger = logging.getLogger(__name__)


def log_session_ready_metric(session: GuestCheckInSession, reservation: Reservation) -> None:
    logger.info(
        "guest_checkin metric session_ready reservation=%s session=%s",
        reservation.pk,
        session.pk,
        extra={
            "metric": "guest_checkin_session_ready",
            "reservation_id": reservation.pk,
            "session_id": session.pk,
            "created_from": session.created_from,
        },
    )


def log_session_completed_metric(session: GuestCheckInSession, reservation: Reservation) -> None:
    ready_to_complete_seconds: int | None = None
    if session.ready_at and session.completed_at:
        delta = session.completed_at - session.ready_at
        ready_to_complete_seconds = int(delta.total_seconds())

    logger.info(
        "guest_checkin metric session_completed reservation=%s session=%s "
        "ready_to_complete_seconds=%s auto_complete=%s",
        reservation.pk,
        session.pk,
        ready_to_complete_seconds,
        ready_to_complete_seconds is not None,
        extra={
            "metric": "guest_checkin_session_completed",
            "reservation_id": reservation.pk,
            "session_id": session.pk,
            "ready_to_complete_seconds": ready_to_complete_seconds,
            "auto_complete": ready_to_complete_seconds is not None,
            "created_from": session.created_from,
        },
    )


def load_guest_checkin_kpis(
    *,
    days: int = 30,
    tenant: Tenant | None = None,
    property: Property | None = None,
) -> GuestCheckInKPIs:
    """Aggregate guest check-in funnel metrics for the last N days."""
    days = max(1, int(days))
    since = timezone.now() - timedelta(days=days)

    sessions = GuestCheckInSession.objects.filter(created_at__gte=since)
    if tenant is not None:
        sessions = sessions.filter(tenant_id=tenant.pk)
    if property is not None:
        sessions = sessions.filter(reservation__property_id=property.pk)

    status_counts = {
        row["status"]: row["count"]
        for row in sessions.values("status").annotate(count=Count("id"))
    }
    sessions_created = sessions.count()
    sessions_completed = status_counts.get(GuestCheckInSessionStatus.COMPLETED, 0)
    sessions_active = status_counts.get(GuestCheckInSessionStatus.ACTIVE, 0)
    sessions_ready_not_completed = sessions.filter(
        status=GuestCheckInSessionStatus.ACTIVE,
        ready_at__isnull=False,
    ).count()

    completed_qs = sessions.filter(status=GuestCheckInSessionStatus.COMPLETED)
    auto_complete_count = completed_qs.filter(ready_at__isnull=False).count()

    ready_to_complete: list[float] = []
    for row in completed_qs.filter(ready_at__isnull=False).values(
        "ready_at",
        "completed_at",
    ):
        ready_at = row["ready_at"]
        completed_at = row["completed_at"]
        if ready_at and completed_at:
            ready_to_complete.append((completed_at - ready_at).total_seconds())

    created_to_ready: list[float] = []
    for row in sessions.filter(ready_at__isnull=False).values("created_at", "ready_at"):
        created_at = row["created_at"]
        ready_at = row["ready_at"]
        if created_at and ready_at:
            created_to_ready.append((ready_at - created_at).total_seconds())

    reminder_qs = GuestMessageDraft.objects.filter(
        hint__startswith=HINT_GUEST_WEB_CHECKIN_REMINDER,
        created_at__gte=since,
    )
    if tenant is not None:
        reminder_qs = reminder_qs.filter(tenant_id=tenant.pk)
    if property is not None:
        reminder_qs = reminder_qs.filter(reservation__property_id=property.pk)

    reminders_by_channel: dict[str, dict[str, int]] = {}
    for row in reminder_qs.values("channel").annotate(
        total=Count("id"),
        sent=Count("id", filter=Q(sent_at__isnull=False)),
    ):
        channel = (row["channel"] or "unknown").strip() or "unknown"
        reminders_by_channel[channel] = {
            "total": row["total"],
            "sent": row["sent"],
        }

    ocr_jobs = DocumentIntakeJob.objects.filter(
        source=DocumentIntakeJobSource.WEB_GUEST,
        status=DocumentIntakeJobStatus.APPLIED,
        processed_at__gte=since,
    )
    if tenant is not None:
        ocr_jobs = ocr_jobs.filter(tenant_id=tenant.pk)
    if property is not None:
        ocr_jobs = ocr_jobs.filter(reservation__property_id=property.pk)
    ocr_jobs_applied = ocr_jobs.count()
    ocr_reservation_ids = set(ocr_jobs.values_list("reservation_id", flat=True))

    completed_with_ocr = 0
    completed_manual_only = 0
    for reservation_id in completed_qs.values_list("reservation_id", flat=True).distinct():
        if reservation_id in ocr_reservation_ids:
            completed_with_ocr += 1
        else:
            completed_manual_only += 1

    completion_rate = (
        round(sessions_completed / sessions_created, 4) if sessions_created else None
    )

    return GuestCheckInKPIs(
        lookback_days=days,
        sessions_created=sessions_created,
        sessions_active=sessions_active,
        sessions_ready_not_completed=sessions_ready_not_completed,
        sessions_ready=sessions.filter(ready_at__isnull=False).count(),
        sessions_completed=sessions_completed,
        sessions_expired=status_counts.get(GuestCheckInSessionStatus.EXPIRED, 0),
        sessions_revoked=status_counts.get(GuestCheckInSessionStatus.REVOKED, 0),
        auto_complete_count=auto_complete_count,
        completion_rate=completion_rate,
        created_to_ready_seconds_median=median(created_to_ready) if created_to_ready else None,
        ready_to_complete_seconds_median=median(ready_to_complete) if ready_to_complete else None,
        reminders_sent=reminder_qs.count(),
        reminders_by_channel=reminders_by_channel,
        ocr_jobs_applied=ocr_jobs_applied,
        completed_with_ocr=completed_with_ocr,
        completed_manual_only=completed_manual_only,
    )


def guest_checkin_kpis_to_dict(kpis: GuestCheckInKPIs) -> dict:
    return {
        "lookback_days": kpis.lookback_days,
        "sessions_created": kpis.sessions_created,
        "sessions_active": kpis.sessions_active,
        "sessions_ready_not_completed": kpis.sessions_ready_not_completed,
        "sessions_ready": kpis.sessions_ready,
        "sessions_completed": kpis.sessions_completed,
        "sessions_expired": kpis.sessions_expired,
        "sessions_revoked": kpis.sessions_revoked,
        "auto_complete_count": kpis.auto_complete_count,
        "completion_rate": kpis.completion_rate,
        "created_to_ready_seconds_median": kpis.created_to_ready_seconds_median,
        "ready_to_complete_seconds_median": kpis.ready_to_complete_seconds_median,
        "reminders_sent": kpis.reminders_sent,
        "reminders_by_channel": kpis.reminders_by_channel,
        "ocr_jobs_applied": kpis.ocr_jobs_applied,
        "completed_with_ocr": kpis.completed_with_ocr,
        "completed_manual_only": kpis.completed_manual_only,
    }


def active_checkin_sessions_for_property(
    *,
    tenant: Tenant,
    property: Property,
) -> list[dict]:
    """Operational rows: expected reservations with an active check-in session."""
    sessions = (
        GuestCheckInSession.objects.filter(
            tenant_id=tenant.pk,
            reservation__property_id=property.pk,
            status=GuestCheckInSessionStatus.ACTIVE,
            reservation__status=Reservation.Status.EXPECTED,
        )
        .select_related("reservation")
        .order_by("-last_activity_at", "-id")
    )
    rows: list[dict] = []
    for session in sessions:
        reservation = session.reservation
        progress = checkin_progress_for_reservation(reservation)
        if progress["required_slots"] <= 0:
            continue
        rows.append(
            {
                "reservation_id": reservation.pk,
                "booking_code": reservation.booking_code or "",
                "booker_name": reservation.booker_name or "",
                "check_in": reservation.check_in.isoformat(),
                "session_status": session.status,
                "effective_status": effective_session_status(session, reservation),
                "ready_at": session.ready_at.isoformat() if session.ready_at else None,
                "last_activity_at": (
                    session.last_activity_at.isoformat() if session.last_activity_at else None
                ),
                "progress": progress,
            }
        )
    return rows


def reservations_due_for_checkin_reminder(
    *,
    days_before: int,
    now=None,
) -> list[Reservation]:
    """Reservations with incomplete web check-in N days before arrival (property-local)."""
    from apps.reservations.checkin_readiness import all_required_slots_ready
    from apps.reservations.guest_checkin_session import get_active_session

    now = now or timezone.now()
    days_before = max(int(days_before), 0)
    candidates: list[Reservation] = []

    reservations = (
        Reservation.objects.filter(
            status=Reservation.Status.EXPECTED,
            check_in__gte=now.date(),
        )
        .select_related("property", "tenant")
        .prefetch_related("guests")
    )

    for reservation in reservations:
        prop_now = now
        from apps.core.timezone import property_local_now

        local_now = property_local_now(reservation.property, now=now)
        target_date = local_now.date() + timedelta(days=days_before)
        if reservation.check_in != target_date:
            continue

        session = get_active_session(reservation)
        if session is not None:
            if local_now < session.opens_at:
                continue
        if all_required_slots_ready(reservation):
            continue

        candidates.append(reservation)

    return candidates
