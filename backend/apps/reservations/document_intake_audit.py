"""Audit document intake: OCR-level fixes and match validation."""

from __future__ import annotations

import logging
from typing import Any

from apps.reservations.document_intake_context import DocumentIntakeContext
from apps.reservations.document_intake_completeness import (
    evaluate_completeness,
    unassigned_image_indices,
)
from apps.reservations.document_intake_match import (
    _booker_first_name_key,
    _person_first_name_key,
    enforce_unique_guest_assignments,
    match_persons_to_guests,
)
from apps.reservations.document_intake_ocr_fixup import normalize_document_number
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus, Guest, Reservation

logger = logging.getLogger(__name__)

MATCHER_FIELDS = frozenset({
    "guest_id",
    "person_index",
    "person_name",
    "guest_name",
    "reservation_id",
    "reservation_label",
    "confidence",
    "candidates",
})

VALIDATOR_FIELDS = frozenset({
    "auto_apply",
    "audit_status",
    "reject_reason",
})


def _merge_duplicate_persons(persons: list[dict]) -> tuple[list[dict], list[str]]:
    """Collapse two persons[] rows with the same document number."""
    actions: list[str] = []
    by_doc: dict[str, dict] = {}
    merged: list[dict] = []

    for idx, person in enumerate(persons):
        if not isinstance(person, dict):
            continue
        doc = normalize_document_number(str(person.get("document_number") or ""))
        if doc and doc in by_doc:
            existing = by_doc[doc]
            for key in ("front_image_index", "back_image_index", "mrz_lines", "face_bbox"):
                if existing.get(key) in (None, [], "") and person.get(key):
                    existing[key] = person[key]
            for key in (
                "given_names", "surnames", "nationality", "date_of_birth",
                "date_of_expiry", "sex", "address", "document_type",
            ):
                if not (existing.get(key) or "").strip() and (person.get(key) or "").strip():
                    existing[key] = person[key]
            actions.append(f"duplicate_person:merged_{idx}")
            continue
        copy = dict(person)
        merged.append(copy)
        if doc:
            by_doc[doc] = copy

    return merged, actions


def _heuristic_unassigned_pairs(
    *,
    persons: list[dict],
    images: list,
    image_count: int,
) -> tuple[list[dict], list[str]]:
    """Two consecutive unassigned indices with front/back → suggest new person."""
    actions: list[str] = []
    unassigned = unassigned_image_indices(persons=persons, image_count=image_count)
    if len(unassigned) < 2:
        return persons, actions

    side_by_index: dict[int, str] = {}
    for img in images:
        sort_order = getattr(img, "sort_order", None)
        if sort_order is None:
            continue
        side = (getattr(img, "detected_side", None) or "").strip().lower()
        if side:
            side_by_index[int(sort_order)] = side

    extra: list[dict] = []
    for i in range(len(unassigned) - 1):
        a, b = unassigned[i], unassigned[i + 1]
        if b != a + 1:
            continue
        side_a = side_by_index.get(a, "")
        side_b = side_by_index.get(b, "")
        if side_a == "front" and side_b == "back":
            extra.append({"front_image_index": a, "back_image_index": b, "document_type": "national_id"})
            actions.append(f"unassigned_pair_heuristic:{a}-{b}")
        elif side_a == "back" and side_b == "front":
            extra.append({"front_image_index": b, "back_image_index": a, "document_type": "national_id"})
            actions.append(f"unassigned_pair_heuristic:{b}-{a}")

    if not extra:
        return persons, actions
    return [*persons, *extra], actions


def audit_document_intake_persons(
    *,
    reservation: Reservation | None,
    persons: list[dict],
    images: list,
    ocr_result: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """OCR-level audit: dedupe persons, unassigned pair heuristic, under-extracted flag."""
    actions: list[str] = []
    persons, dup_actions = _merge_duplicate_persons(persons)
    actions.extend(dup_actions)

    image_count = len(images)
    persons, pair_actions = _heuristic_unassigned_pairs(
        persons=persons,
        images=images,
        image_count=image_count,
    )
    actions.extend(pair_actions)

    if reservation is not None:
        completeness = evaluate_completeness(
            reservation=reservation,
            persons=persons,
            matches=[],
            images=images,
        )
        if completeness.ocr_under_extracted and ocr_result and not (ocr_result.get("_orphan_pass") or {}).get("ran"):
            actions.append("under_extracted:orphan_pass_recommended")

    return persons, actions


def audit_document_intake_matches(
    *,
    reservation: Reservation,
    persons: list[dict],
    matches: list[dict],
) -> tuple[list[dict], list[str]]:
    """Business validation only — never remaps matcher output fields."""
    if not persons or not matches:
        return matches, []

    validated = [dict(m) if isinstance(m, dict) else m for m in matches]
    actions: list[str] = []
    booker_first = _booker_first_name_key(reservation)

    for match in validated:
        if not isinstance(match, dict):
            continue
        idx = int(match.get("person_index", -1))
        if idx < 0 or idx >= len(persons):
            continue
        person = persons[idx]
        guest_id = match.get("guest_id")
        if not guest_id:
            continue

        try:
            guest = Guest.objects.get(pk=int(guest_id), reservation_id=reservation.pk)
        except Guest.DoesNotExist:
            continue

        person_first = _person_first_name_key(person)
        if guest.is_primary and booker_first and person_first and booker_first != person_first:
            match["auto_apply"] = False
            match["audit_status"] = "rejected"
            match["reject_reason"] = "booker_first_name_mismatch"
            actions.append(f"rejected:person_{idx}:booker_first_name_mismatch")
            logger.info(
                "document intake audit rejected booker first-name mismatch reservation_id=%s person_index=%s guest_id=%s",
                reservation.pk,
                idx,
                guest.pk,
            )
            continue

        match["audit_status"] = "confirmed"

    return validated, actions


def run_document_intake_matching_pipeline(
    *,
    tenant_id: int,
    persons: list[dict],
    reservation: Reservation | None = None,
    reservation_id: int | None = None,
) -> list[dict]:
    """Run match → enforce_unique → audit (when reservation is known).

    This is the only supported production entry point for document-intake matching.
    Production code must not call ``match_persons_to_guests()`` directly.
    Matcher-only behaviour belongs in tests or private helpers, not production APIs.
    """
    rid: int | None = reservation.pk if reservation is not None else reservation_id
    matches = match_persons_to_guests(
        tenant_id=tenant_id,
        persons=persons,
        reservation_id=rid,
    )
    matches = enforce_unique_guest_assignments(matches)

    audit_reservation = reservation
    if audit_reservation is None and rid is not None:
        audit_reservation = Reservation.objects.prefetch_related("guests").get(pk=rid)

    if audit_reservation is not None:
        matches, _actions = audit_document_intake_matches(
            reservation=audit_reservation,
            persons=persons,
            matches=matches,
        )
    return matches


def rematch_and_audit_job(ctx: DocumentIntakeContext) -> list[dict]:
    """Re-run matching pipeline and persist matches on the job."""
    job = ctx.job
    reservation = ctx.reservation
    if reservation is None:
        return list(job.matches or [])

    persons = (job.ocr_result or {}).get("persons") or []
    matches = run_document_intake_matching_pipeline(
        tenant_id=ctx.effective_tenant_id,
        reservation=reservation,
        persons=persons,
    )
    job.matches = matches
    job.save(update_fields=["matches", "updated_at"])
    return matches


def try_apply_complete_job(ctx: DocumentIntakeContext) -> list[dict[str, Any]]:
    """Apply job when OCR is done, matches complete, but applied_result is empty."""
    job = ctx.job
    reservation = ctx.reservation
    if reservation is None:
        return []
    if job.status not in {DocumentIntakeJobStatus.DONE, DocumentIntakeJobStatus.APPLIED}:
        return []

    persons = (job.ocr_result or {}).get("persons") or []
    images = list(job.images.order_by("sort_order", "id"))
    matches = list(job.matches or [])
    completeness = evaluate_completeness(
        reservation=reservation,
        persons=persons,
        matches=matches,
        images=images,
    )
    if not completeness.is_complete:
        return []

    if job.applied_result:
        return list(job.applied_result)

    from apps.reservations.document_intake_service import apply_document_intake_job

    return apply_document_intake_job(ctx, whatsapp_reply=False)


def assert_audit_only_touched_validator_fields(before: dict, after: dict) -> None:
    """Test helper: audit may only change validator output fields."""
    for field in MATCHER_FIELDS:
        if before.get(field) != after.get(field):
            raise AssertionError(f"audit mutated matcher field {field!r}")
