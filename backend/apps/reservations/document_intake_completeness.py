"""Pre-apply audit: adult guest slots, ID sides, and unmatched OCR persons."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.integrations.whatsapp.apply_reply import adult_guests_for_registration
from apps.reservations.document_intake_service import _resolve_side_images
from apps.reservations.document_intake_sides import (
    MissingIdSide,
    _guest_treat_as_passport,
    _has_photo,
)
from apps.reservations.guest_slots import ensure_guest_slots_for_intake, is_unfilled_guest, PLACEHOLDER_NAME
from apps.reservations.models import Guest, Reservation


@dataclass(frozen=True)
class MissingGuest:
    guest_id: int
    guest_name: str
    adult_ordinal: int


@dataclass(frozen=True)
class UnmatchedPerson:
    person_index: int
    display_name: str


@dataclass
class DocumentIntakeCompleteness:
    is_complete: bool
    missing_guests: list[MissingGuest] = field(default_factory=list)
    missing_sides: list[MissingIdSide] = field(default_factory=list)
    unmatched_persons: list[UnmatchedPerson] = field(default_factory=list)


def _guest_display_name(guest: Guest) -> str:
    name = (guest.name or f"{guest.first_name} {guest.last_name}".strip()).strip()
    return name or f"Guest #{guest.pk}"


def _person_display_name(person: dict) -> str:
    given = str(person.get("given_names") or "").strip()
    surnames = str(person.get("surnames") or "").strip()
    if given and surnames:
        return f"{given} {surnames}"
    return given or surnames or "Osoba na dokumentu"


def _missing_sides_for_matched_guest(
    *,
    guest: Guest,
    person: dict,
    images: list,
    guest_name: str,
) -> list[MissingIdSide]:
    """Batch OCR gaps merged with photos already stored on the guest (incremental capture)."""
    doc_type = str(person.get("document_type") or "national_id").lower()
    is_passport = doc_type == "passport"

    front_idx = person.get("front_image_index")
    back_idx = person.get("back_image_index")
    _, _, applying_front, applying_back = _resolve_side_images(
        images, front_idx, back_idx, is_passport=is_passport,
    )

    id_docs = list(guest.id_documents.all())
    treat_as_passport = is_passport or _guest_treat_as_passport(guest=guest, id_docs=id_docs)

    if treat_as_passport:
        has_front = any(_has_photo(id_doc.front_photo) for id_doc in id_docs) or applying_front
        if not has_front:
            return [MissingIdSide(guest.pk, guest_name, "front", is_passport=True)]
        return []

    has_front = any(_has_photo(id_doc.front_photo) for id_doc in id_docs) or applying_front
    has_back = any(_has_photo(id_doc.back_photo) for id_doc in id_docs) or applying_back

    gaps: list[MissingIdSide] = []
    if not has_front:
        gaps.append(MissingIdSide(guest.pk, guest_name, "front", is_passport=False))
    elif not has_back:
        gaps.append(MissingIdSide(guest.pk, guest_name, "back", is_passport=False))
    return gaps


def evaluate_completeness(
    *,
    reservation: Reservation,
    persons: list[dict],
    matches: list[dict],
    images: list,
) -> DocumentIntakeCompleteness:
    """Simulate apply prerequisites without mutating guest rows."""
    if not isinstance(persons, list):
        persons = []
    if not isinstance(matches, list):
        matches = []

    ensure_guest_slots_for_intake(
        tenant=reservation.tenant,
        reservation=reservation,
        min_count=len(persons),
    )
    adults = adult_guests_for_registration(reservation)
    guest_by_id = {guest.pk: guest for guest in reservation.guests.all()}

    match_by_person: dict[int, dict] = {}
    for match in matches:
        if not isinstance(match, dict):
            continue
        try:
            idx = int(match.get("person_index", -1))
        except (TypeError, ValueError):
            continue
        if idx >= 0:
            match_by_person[idx] = match

    matched_guest_ids: set[int] = set()
    missing_sides: list[MissingIdSide] = []
    unmatched_persons: list[UnmatchedPerson] = []

    for idx, person in enumerate(persons):
        if not isinstance(person, dict):
            continue
        match = match_by_person.get(idx)
        if not match or not match.get("auto_apply") or not match.get("guest_id"):
            unmatched_persons.append(
                UnmatchedPerson(person_index=idx, display_name=_person_display_name(person))
            )
            continue

        guest_id = int(match["guest_id"])
        matched_guest_ids.add(guest_id)
        guest_name = str(match.get("guest_name") or "").strip() or _person_display_name(person)
        guest = guest_by_id.get(guest_id)
        if guest is None:
            continue
        missing_sides.extend(
            _missing_sides_for_matched_guest(
                guest=guest,
                person=person,
                images=images,
                guest_name=guest_name,
            )
        )

    missing_guests: list[MissingGuest] = []
    for ordinal, guest in enumerate(adults, start=1):
        if guest.pk in matched_guest_ids:
            continue
        name = _guest_display_name(guest)
        if is_unfilled_guest(guest) or name == PLACEHOLDER_NAME:
            label = f"{PLACEHOLDER_NAME} ({ordinal}. odrasli)"
        else:
            label = name
        missing_guests.append(
            MissingGuest(guest_id=guest.pk, guest_name=label, adult_ordinal=ordinal)
        )

    is_complete = not missing_guests and not missing_sides and not unmatched_persons
    return DocumentIntakeCompleteness(
        is_complete=is_complete,
        missing_guests=missing_guests,
        missing_sides=missing_sides,
        unmatched_persons=unmatched_persons,
    )
