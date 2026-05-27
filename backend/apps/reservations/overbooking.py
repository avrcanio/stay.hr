from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from apps.properties.models import Unit
from apps.reservations.availability import BLOCKING_RESERVATION_STATUSES, unit_has_blocking_overlap
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

OVERBOOKING_NOTE_PREFIX = "OVERBOOKING:"


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
            reservation__status__in=Reservation.OPERATIONAL_STATUSES
            - {Reservation.Status.CANCELED, Reservation.Status.NO_SHOW},
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


def _incumbent_reservation_for_unit(
    *,
    tenant: Tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
    exclude_reservation_id: int,
) -> Reservation | None:
    row = (
        ReservationUnit.objects.filter(
            tenant=tenant,
            unit=unit,
            reservation__status__in=BLOCKING_RESERVATION_STATUSES,
            reservation__check_in__lt=check_out,
            reservation__check_out__gt=check_in,
        )
        .exclude(reservation_id=exclude_reservation_id)
        .select_related("reservation")
        .order_by("reservation__check_in", "reservation__booked_at", "reservation_id")
        .first()
    )
    return row.reservation if row else None


def find_ingest_conflicts(reservation: Reservation) -> list[tuple[Unit, Reservation]]:
    if reservation.status in {Reservation.Status.CANCELED, Reservation.Status.NO_SHOW}:
        return []

    conflicts: list[tuple[Unit, Reservation]] = []
    for row in ReservationUnit.objects.filter(reservation=reservation).select_related("unit"):
        if row.unit is None:
            continue
        if not unit_has_blocking_overlap(
            reservation.tenant,
            row.unit_id,
            reservation.check_in,
            reservation.check_out,
            exclude_reservation_id=reservation.pk,
        ):
            continue
        incumbent = _incumbent_reservation_for_unit(
            tenant=reservation.tenant,
            unit=row.unit,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            exclude_reservation_id=reservation.pk,
        )
        if incumbent is not None:
            conflicts.append((row.unit, incumbent))
    return conflicts


def _format_ingest_overbooking_note(
    reservation: Reservation,
    conflicts: list[tuple[Unit, Reservation]],
) -> str:
    lines = [
        f"{OVERBOOKING_NOTE_PREFIX} unit zauzet pri ingestu ({reservation.import_source}).",
    ]
    for unit, incumbent in conflicts:
        incumbent_code = incumbent.booking_code or incumbent.external_id or str(incumbent.pk)
        lines.append(
            f"- {unit.code}: postojeća rezervacija {incumbent_code} "
            f"({incumbent.booker_name}, {incumbent.check_in}..{incumbent.check_out})"
        )
    return "\n".join(lines)


def _notify_ingest_overbooking(reservation: Reservation, conflicts: list[tuple[Unit, Reservation]]) -> None:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data

    unit_codes = ", ".join(unit.code for unit, _ in conflicts)
    incumbent_codes = ", ".join(
        incumbent.booking_code or incumbent.external_id or str(incumbent.pk)
        for _, incumbent in conflicts
    )
    title = "Overbooking pri ingestu"
    body = (
        f"{reservation.booker_name} · {unit_codes} · preklapanje s {incumbent_codes}"
    )
    data = reception_push_data(
        event_type="reservation.overbooking",
        reservation_id=reservation.pk,
        summary=body,
        booking_code=reservation.booking_code or str(reservation.pk),
        check_in=reservation.check_in.isoformat(),
        check_out=reservation.check_out.isoformat(),
        status=reservation.status,
        tenant_id=str(reservation.tenant_id),
    )
    send_tenant_reception_push(
        tenant_id=reservation.tenant_id,
        title=title,
        body=body,
        data=data,
    )


def flag_ingest_overbooking(reservation: Reservation) -> list[tuple[Unit, Reservation]]:
    """Append overbooking warning to notes and alert reception when unit is already occupied."""
    conflicts = find_ingest_conflicts(reservation)
    if not conflicts:
        return []

    note = _format_ingest_overbooking_note(reservation, conflicts)
    existing = (reservation.notes or "").strip()
    if OVERBOOKING_NOTE_PREFIX not in existing:
        reservation.notes = f"{existing}\n{note}".strip() if existing else note
        reservation.save(update_fields=["notes", "updated_at"])

    logger.warning(
        "overbooking detected on ingest",
        extra={
            "reservation_id": reservation.pk,
            "booking_code": reservation.booking_code,
            "import_source": reservation.import_source,
            "units": [unit.code for unit, _ in conflicts],
            "incumbent_ids": [incumbent.pk for _, incumbent in conflicts],
        },
    )
    _notify_ingest_overbooking(reservation, conflicts)
    return conflicts
