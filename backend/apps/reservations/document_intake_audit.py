"""Audit and auto-correct document intake guest matches."""

from __future__ import annotations

import logging
from typing import Any

from apps.reservations.document_intake_completeness import (
    evaluate_completeness,
    unassigned_image_indices,
)
from apps.reservations.document_intake_match import (
    _booker_first_name_key,
    _booker_person_overlap,
    _person_first_name_key,
    _person_name_keys,
    _person_surname_tokens,
    _reservation_label,
    match_persons_to_guests,
)
from apps.reservations.document_intake_ocr_fixup import normalize_document_number
from apps.reservations.guest_slots import PLACEHOLDER_NAME, is_unfilled_guest
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus, Guest, Reservation

logger = logging.getLogger(__name__)


def _is_placeholder_guest(guest: Guest) -> bool:
    name = (guest.name or "").strip()
    if name == PLACEHOLDER_NAME:
        return True
    first = (guest.first_name or "").strip()
    last = (guest.last_name or "").strip()
    return first == "Novi" and last == "gost"


def _guest_display_name(guest: Guest) -> str:
    stored = (guest.name or "").strip()
    if stored:
        return stored
    return f"{guest.first_name} {guest.last_name}".strip()


def _primary_unfilled_guest(reservation: Reservation) -> Guest | None:
    for guest in reservation.guests.all():
        if guest.is_primary and is_unfilled_guest(guest):
            return guest
    return None


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
    """Correct common match mistakes (e.g. booker OCR assigned to placeholder slot)."""
    if not persons or not matches:
        return matches, []

    corrected = [dict(m) if isinstance(m, dict) else m for m in matches]
    actions: list[str] = []

    for match in corrected:
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

        if not _is_placeholder_guest(guest):
            continue

        keys = _person_name_keys(person)
        surnames = _person_surname_tokens(person)
        if not _booker_person_overlap(reservation, keys, surnames):
            continue

        booker_first = _booker_first_name_key(reservation)
        person_first = _person_first_name_key(person)
        if booker_first and person_first and booker_first != person_first:
            continue

        primary = _primary_unfilled_guest(reservation)
        if primary is None or primary.pk == guest.pk:
            continue

        match["guest_id"] = primary.pk
        match["guest_name"] = _guest_display_name(primary)
        match["reservation_id"] = reservation.pk
        match["reservation_label"] = _reservation_label(reservation)
        match["auto_apply"] = True
        actions.append(f"wrong_slot:person_{idx}->guest_{primary.pk}")
        logger.info(
            "document intake audit corrected wrong slot reservation_id=%s person_index=%s guest_id=%s",
            reservation.pk,
            idx,
            primary.pk,
        )

    return corrected, actions


def rematch_and_audit_job(job: DocumentIntakeJob, *, reservation: Reservation | None = None) -> list[dict]:
    """Re-run matching and apply audit corrections."""
    if reservation is None:
        if not job.reservation_id:
            return list(job.matches or [])
        reservation = Reservation.objects.prefetch_related("guests").get(pk=job.reservation_id)

    persons = (job.ocr_result or {}).get("persons") or []
    matches = match_persons_to_guests(
        tenant_id=job.tenant_id,
        persons=persons,
        reservation_id=reservation.pk,
    )
    matches, _actions = audit_document_intake_matches(
        reservation=reservation,
        persons=persons,
        matches=matches,
    )
    job.matches = matches
    job.save(update_fields=["matches", "updated_at"])
    return matches


def try_apply_complete_job(job: DocumentIntakeJob, *, reservation: Reservation) -> list[dict[str, Any]]:
    """Apply job when OCR is done, matches complete, but applied_result is empty."""
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

    return apply_document_intake_job(job.pk, whatsapp_reply=False)
