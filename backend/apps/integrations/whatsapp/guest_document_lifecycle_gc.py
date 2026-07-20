"""Idempotent GC helpers and event hooks for WhatsApp document intake lifecycle."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction

from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    Reservation,
    WhatsAppDocumentBatchSession,
    WhatsAppDocumentBatchStatus,
)

logger = logging.getLogger(__name__)

_ACTIVE_BATCH_SESSION_STATUSES = frozenset(
    {
        WhatsAppDocumentBatchStatus.COLLECTING,
        WhatsAppDocumentBatchStatus.PROCESSING,
        WhatsAppDocumentBatchStatus.AWAITING_CONFIRM,
        WhatsAppDocumentBatchStatus.AFTER_NO,
    }
)

_STUCK_JOB_STATUSES = frozenset(
    {
        DocumentIntakeJobStatus.QUEUED,
        DocumentIntakeJobStatus.PROCESSING,
        DocumentIntakeJobStatus.DONE,
    }
)


@dataclass(frozen=True)
class CloseResult:
    closed: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class SupersedeResult:
    superseded: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class LifecycleGcResult:
    sessions_closed: list[int] = field(default_factory=list)
    sessions_skipped: list[int] = field(default_factory=list)
    jobs_superseded: list[int] = field(default_factory=list)
    jobs_skipped: list[int] = field(default_factory=list)


def _superseded_by_job_marker(by_job_id: int) -> str:
    return f"superseded_by_job:{by_job_id}"


def _lifecycle_gc_marker(reason: str) -> str:
    return f"lifecycle_gc;reason={reason}"


def _is_supersedable_stuck_job(job: DocumentIntakeJob) -> bool:
    if job.status == DocumentIntakeJobStatus.APPLIED:
        return False
    if job.status == DocumentIntakeJobStatus.FAILED:
        return False
    if job.status not in _STUCK_JOB_STATUSES:
        return False
    if job.status == DocumentIntakeJobStatus.DONE and job.applied_result:
        return False
    return True


def _job_already_superseded(
    job: DocumentIntakeJob,
    *,
    by_job_id: int | None,
    reason: str,
) -> bool:
    msg = job.error_message or ""
    if by_job_id is not None:
        return _superseded_by_job_marker(by_job_id) in msg
    return _lifecycle_gc_marker(reason) in msg


def close_stale_batch_sessions(
    reservation: Reservation,
    *,
    reason: str,
    exclude_session_id: int | None = None,
) -> CloseResult:
    """Close active batch sessions for a reservation (idempotent)."""
    sessions = WhatsAppDocumentBatchSession.objects.filter(
        reservation=reservation,
        status__in=_ACTIVE_BATCH_SESSION_STATUSES,
    )
    if exclude_session_id is not None:
        sessions = sessions.exclude(pk=exclude_session_id)

    closed: list[int] = []
    skipped: list[int] = []
    for session in sessions:
        session.status = WhatsAppDocumentBatchStatus.DONE
        session.save(update_fields=["status", "updated_at"])
        closed.append(session.pk)
        logger.info(
            "lifecycle_closed session_id=%s reason=%s",
            session.pk,
            reason,
        )

    return CloseResult(closed=closed, skipped=skipped)


def close_superseded_batch_sessions(
    reservation: Reservation,
    *,
    keep_session_id: int,
    reason: str,
) -> CloseResult:
    """Close active sessions except the one tied to the successful apply."""
    return close_stale_batch_sessions(
        reservation,
        reason=reason,
        exclude_session_id=keep_session_id,
    )


def supersede_document_intake_job(
    job: DocumentIntakeJob,
    *,
    by_job_id: int | None,
    reason: str,
) -> bool:
    """Mark a stuck job failed with a supersede marker (idempotent)."""
    if not _is_supersedable_stuck_job(job):
        return False
    if _job_already_superseded(job, by_job_id=by_job_id, reason=reason):
        return False

    if by_job_id is not None:
        error_message = f"{_superseded_by_job_marker(by_job_id)}; reason={reason}"
        log_by = by_job_id
    else:
        error_message = f"{_lifecycle_gc_marker(reason)}"
        log_by = None

    job.status = DocumentIntakeJobStatus.FAILED
    job.error_message = error_message
    job.save(update_fields=["status", "error_message", "updated_at"])
    logger.info(
        "lifecycle_superseded job_id=%s by_job_id=%s reason=%s",
        job.pk,
        log_by,
        reason,
    )
    return True


def supersede_stuck_jobs(
    reservation: Reservation,
    *,
    reason: str,
    by_job_id: int | None = None,
) -> SupersedeResult:
    """Supersede stuck WhatsApp intake jobs for a reservation (idempotent)."""
    jobs = DocumentIntakeJob.objects.filter(
        reservation=reservation,
        source=DocumentIntakeJobSource.WHATSAPP,
    )
    if by_job_id is not None:
        jobs = jobs.exclude(pk=by_job_id)

    superseded: list[int] = []
    skipped: list[int] = []
    for job in jobs:
        if supersede_document_intake_job(job, by_job_id=by_job_id, reason=reason):
            superseded.append(job.pk)
        else:
            skipped.append(job.pk)

    return SupersedeResult(superseded=superseded, skipped=skipped)


def run_lifecycle_gc(
    reservation: Reservation,
    *,
    reason: str,
    by_job_id: int | None = None,
    keep_session_id: int | None = None,
    supersede_jobs: bool = True,
) -> LifecycleGcResult:
    """Close sessions and optionally supersede stuck jobs in one transaction."""
    with transaction.atomic():
        if keep_session_id is not None:
            close_result = close_superseded_batch_sessions(
                reservation,
                keep_session_id=keep_session_id,
                reason=reason,
            )
        else:
            close_result = close_stale_batch_sessions(reservation, reason=reason)

        if supersede_jobs:
            supersede_result = supersede_stuck_jobs(
                reservation,
                reason=reason,
                by_job_id=by_job_id,
            )
        else:
            supersede_result = SupersedeResult()

    if close_result.closed or supersede_result.superseded:
        logger.info(
            "reconcile_gc reservation_id=%s sessions_closed=%s jobs_superseded=%s reason=%s",
            reservation.pk,
            len(close_result.closed),
            len(supersede_result.superseded),
            reason,
        )

    return LifecycleGcResult(
        sessions_closed=close_result.closed,
        sessions_skipped=close_result.skipped,
        jobs_superseded=supersede_result.superseded,
        jobs_skipped=supersede_result.skipped,
    )


def on_document_intake_applied(job: DocumentIntakeJob) -> LifecycleGcResult | None:
    """After a successful WhatsApp apply: close parallel sessions, supersede stuck jobs."""
    if job.status != DocumentIntakeJobStatus.APPLIED:
        return None
    if job.source != DocumentIntakeJobSource.WHATSAPP or not job.reservation_id:
        return None

    reservation = job.reservation
    keep_session_id = (
        WhatsAppDocumentBatchSession.objects.filter(reservation=reservation, job=job)
        .values_list("pk", flat=True)
        .first()
    )

    return run_lifecycle_gc(
        reservation,
        reason="document_intake_applied",
        by_job_id=job.pk,
        keep_session_id=keep_session_id,
    )


def on_guest_document_intake_blocked(
    reservation: Reservation,
    *,
    reason: str,
) -> LifecycleGcResult:
    """Waive or check-in complete: close all active sessions and supersede stuck jobs."""
    return run_lifecycle_gc(reservation, reason=reason)


def on_reservation_terminal_status(
    reservation: Reservation,
    *,
    reason: str,
) -> CloseResult:
    """Terminal reservation status: close active sessions only."""
    return close_stale_batch_sessions(reservation, reason=reason)
