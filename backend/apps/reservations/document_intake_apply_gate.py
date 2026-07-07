"""Safe-apply gate for partial document intake apply."""

from __future__ import annotations

from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus


def matches_safe_for_auto_apply(matches: list[dict]) -> bool:
    auto = [m for m in matches if m.get("auto_apply") and m.get("guest_id")]
    return len(auto) == len({int(m["guest_id"]) for m in auto})


def job_eligible_for_partial_apply(job: DocumentIntakeJob) -> bool:
    if job.status == DocumentIntakeJobStatus.APPLIED:
        return False
    if job.applied_result:
        return False
    return True


def safe_to_partial_apply(job: DocumentIntakeJob, matches: list[dict]) -> bool:
    return job_eligible_for_partial_apply(job) and matches_safe_for_auto_apply(matches)
