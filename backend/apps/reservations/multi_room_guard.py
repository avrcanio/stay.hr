from __future__ import annotations

import logging
from datetime import date

from django.db.models import Q

from apps.integrations.channex.booking_room_mismatch import (
    detect_stay_hr_unit_gaps,
    reconcile_reservation_units,
)
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset(
    {
        Reservation.Status.PENDING,
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)


def find_multi_room_inventory_gaps(
    *,
    tenant: Tenant,
    from_date: date | None = None,
) -> list[dict]:
    """
    Reservations where units_count implies multi-room but ReservationUnit rows are incomplete.
    """
    qs = Reservation.objects.filter(
        tenant=tenant,
        status__in=ACTIVE_STATUSES,
    ).filter(Q(units_count__gte=2) | Q(import_source="booking_pdf"))
    if from_date is not None:
        qs = qs.filter(check_out__gt=from_date)

    gaps: list[dict] = []
    for reservation in qs.order_by("check_in", "pk").iterator():
        issues = detect_stay_hr_unit_gaps(reservation)
        if not issues:
            continue
        gaps.append(
            {
                "reservation_id": reservation.pk,
                "booking_code": reservation.booking_code,
                "booker_name": reservation.booker_name,
                "check_in": reservation.check_in,
                "check_out": reservation.check_out,
                "units_count": reservation.units_count,
                "import_source": reservation.import_source,
                "issues": issues,
            }
        )
    return gaps


def find_channex_calendar_mismatches(
    *,
    tenant: Tenant,
    from_date: date | None = None,
) -> list[dict]:
    """stay.hr has 2+ mapped units but Channex revision reports fewer rooms."""
    qs = Reservation.objects.filter(
        tenant=tenant,
        status__in=ACTIVE_STATUSES,
        import_source="channex",
    )
    if from_date is not None:
        qs = qs.filter(check_out__gt=from_date)

    gaps: list[dict] = []
    for reservation in qs.order_by("check_in", "pk").iterator():
        report = reconcile_reservation_units(reservation)
        mapped = int(report.get("mapped_units") or 0)
        channex_rooms = report.get("channex_rooms")
        if mapped < 2:
            continue
        if channex_rooms is None or channex_rooms >= mapped:
            continue
        issues = report.get("issues") or [
            f"Channex rooms={channex_rooms}, stay.hr mapped={mapped}"
        ]
        gaps.append(
            {
                "reservation_id": reservation.pk,
                "booking_code": reservation.booking_code,
                "booker_name": reservation.booker_name,
                "check_in": reservation.check_in,
                "check_out": reservation.check_out,
                "units_count": reservation.units_count,
                "import_source": reservation.import_source,
                "issues": issues,
            }
        )
    return gaps


def find_all_multi_room_gaps(
    *,
    tenant: Tenant,
    from_date: date | None = None,
) -> list[dict]:
    """Unit mapping gaps + Channex calendar mismatches (deduped by reservation_id)."""
    seen: set[int] = set()
    merged: list[dict] = []
    for gap in (
        find_multi_room_inventory_gaps(tenant=tenant, from_date=from_date)
        + find_channex_calendar_mismatches(tenant=tenant, from_date=from_date)
    ):
        rid = gap["reservation_id"]
        if rid in seen:
            continue
        seen.add(rid)
        merged.append(gap)
    return merged


def push_channex_for_gap_reservation(reservation_id: int) -> dict:
    from apps.integrations.channex.reservation_availability_service import (
        push_reservation_channex_availability_unconditional,
    )
    from apps.reservations.models import Reservation

    reservation = Reservation.objects.filter(pk=reservation_id).first()
    if reservation is None:
        return {"skipped": True, "reason": "not_found"}
    return push_reservation_channex_availability_unconditional(reservation)


def notify_multi_room_gaps(tenant: Tenant, gaps: list[dict]) -> None:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data

    lines = []
    for gap in gaps[:5]:
        code = gap["booking_code"] or gap["reservation_id"]
        lines.append(
            f"{code} {gap['check_in']}: {gap['issues'][0]}"
        )
    if len(gaps) > 5:
        lines.append(f"+{len(gaps) - 5} još")

    body = "; ".join(lines)
    first = gaps[0]
    data = reception_push_data(
        event_type="reservation.multi_room_gap",
        reservation_id=first["reservation_id"],
        summary=body,
        booking_code=first.get("booking_code") or "",
        check_in=first["check_in"].isoformat(),
        check_out=first["check_out"].isoformat(),
        status="",
        tenant_id=str(tenant.pk),
    )
    send_tenant_reception_push(
        tenant_id=tenant.pk,
        title=f"Multi-room inventar ({len(gaps)})",
        body=body,
        data=data,
    )
