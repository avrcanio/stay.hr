"""Immutable context for document intake pipeline — tenant/reservation source of truth."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from apps.reservations.models import DocumentIntakeJob, Reservation

logger = logging.getLogger(__name__)


class DocumentIntakeTenantMismatchError(ValueError):
    """Job tenant_id does not match reservation.tenant_id on create path."""


def _heal_job_tenant_mismatch(job: DocumentIntakeJob, reservation: Reservation) -> None:
    logger.error(
        "document_intake tenant mismatch healed job_id=%s job_tenant=%s reservation_tenant=%s",
        job.pk,
        job.tenant_id,
        reservation.tenant_id,
    )
    job.tenant_id = reservation.tenant_id
    job.save(update_fields=["tenant_id", "updated_at"])


def ensure_job_tenant_matches_reservation(
    job: DocumentIntakeJob,
    reservation: Reservation | None,
    *,
    raise_on_mismatch: bool | None = None,
) -> None:
    """Set job.tenant_id from reservation before save; raise if inconsistent on create path."""
    if reservation is None:
        return
    expected = reservation.tenant_id
    if job.tenant_id == expected:
        return
    if raise_on_mismatch is None:
        raise_on_mismatch = settings.DEBUG or getattr(settings, "TESTING", False)
    if raise_on_mismatch:
        raise DocumentIntakeTenantMismatchError(
            f"job tenant_id={job.tenant_id} != reservation tenant_id={expected}"
        )
    job.tenant_id = expected


@dataclass(frozen=True)
class DocumentIntakeContext:
    job: DocumentIntakeJob
    reservation: Reservation | None
    effective_tenant_id: int

    @property
    def is_reservation_scoped(self) -> bool:
        return self.reservation is not None

    @classmethod
    def from_job(cls, job: DocumentIntakeJob) -> DocumentIntakeContext:
        reservation = None
        effective_tenant_id = job.tenant_id

        if job.reservation_id:
            reservation = Reservation.objects.select_related("tenant", "property").get(
                pk=job.reservation_id
            )
            if job.tenant_id != reservation.tenant_id:
                _heal_job_tenant_mismatch(job, reservation)
                job.refresh_from_db(fields=["tenant_id", "updated_at"])
            effective_tenant_id = reservation.tenant_id

        return cls(
            job=job,
            reservation=reservation,
            effective_tenant_id=effective_tenant_id,
        )
