from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from apps.properties.models import Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant


@dataclass(frozen=True)
class OverbookingConflict:
    unit: Unit
    overlap_from: date
    overlap_to: date
    incumbent: Reservation
    conflicting: Reservation


def _reservation_rank(reservation: Reservation) -> tuple[date, datetime, int]:
    tie_breaker = reservation.booked_at or reservation.created_at
    return (reservation.check_in, tie_breaker, reservation.pk)


def _dates_overlap(
    left_in: date,
    left_out: date,
    right_in: date,
    right_out: date,
) -> bool:
    return left_in < right_out and right_in < left_out


def _overlap_range(
    left_in: date,
    left_out: date,
    right_in: date,
    right_out: date,
) -> tuple[date, date]:
    return max(left_in, right_in), min(left_out, right_out)


def pick_incumbent_and_conflicting(
    left: Reservation,
    right: Reservation,
) -> tuple[Reservation, Reservation]:
    if _reservation_rank(left) <= _reservation_rank(right):
        return left, right
    return right, left


def find_conflicts(
    *,
    tenant: Tenant,
    from_date: date | None = None,
) -> list[OverbookingConflict]:
    unit_rows = (
        ReservationUnit.objects.filter(
            tenant=tenant,
            unit_id__isnull=False,
            reservation__status__in=Reservation.OPERATIONAL_STATUSES - {Reservation.Status.CANCELED},
        )
        .select_related("unit", "reservation")
        .order_by("unit_id", "reservation_id")
    )
    if from_date is not None:
        unit_rows = unit_rows.filter(reservation__check_out__gt=from_date)

    by_unit: dict[int, list[tuple[ReservationUnit, Reservation]]] = {}
    for row in unit_rows:
        by_unit.setdefault(row.unit_id, []).append((row, row.reservation))

    conflicts: list[OverbookingConflict] = []
    seen_pairs: set[tuple[int, int, int]] = set()

    for entries in by_unit.values():
        for idx, (left_row, left_reservation) in enumerate(entries):
            for right_row, right_reservation in entries[idx + 1 :]:
                if left_reservation.pk == right_reservation.pk:
                    continue
                if not _dates_overlap(
                    left_reservation.check_in,
                    left_reservation.check_out,
                    right_reservation.check_in,
                    right_reservation.check_out,
                ):
                    continue

                pair_key = (
                    left_row.unit_id,
                    min(left_reservation.pk, right_reservation.pk),
                    max(left_reservation.pk, right_reservation.pk),
                )
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                incumbent, conflicting = pick_incumbent_and_conflicting(
                    left_reservation,
                    right_reservation,
                )
                overlap_from, overlap_to = _overlap_range(
                    incumbent.check_in,
                    incumbent.check_out,
                    conflicting.check_in,
                    conflicting.check_out,
                )
                conflicts.append(
                    OverbookingConflict(
                        unit=left_row.unit,
                        overlap_from=overlap_from,
                        overlap_to=overlap_to,
                        incumbent=incumbent,
                        conflicting=conflicting,
                    )
                )

    conflicts.sort(
        key=lambda conflict: (
            conflict.unit.code,
            conflict.overlap_from,
            conflict.incumbent.check_in,
            conflict.conflicting.check_in,
        )
    )
    return conflicts
