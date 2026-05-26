from __future__ import annotations

from datetime import date

from apps.reservations.models import Guest

EVISITOR_MIN_AGE = 18


def _age_on(reference: date, dob: date) -> int:
    years = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        years -= 1
    return years


def guest_requires_evisitor(guest: Guest, *, reference_date: date | None = None) -> bool:
    """True when guest must be registered in eVisitor (18+ on reference date)."""
    if guest.date_of_birth is None:
        return True
    ref = reference_date
    if ref is None:
        ref = guest.reservation.check_in
    return _age_on(ref, guest.date_of_birth) >= EVISITOR_MIN_AGE
