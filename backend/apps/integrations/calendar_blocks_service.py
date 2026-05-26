from __future__ import annotations

from datetime import date

from apps.integrations.models import UnitAvailabilityBlock
from apps.properties.models import Unit
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class CalendarBlockError(Exception):
    pass


def _serialize_block(row: UnitAvailabilityBlock) -> dict:
    return {
        "id": row.id,
        "unit_id": row.unit_id,
        "unit_code": row.unit.code,
        "check_in": row.check_in.isoformat(),
        "check_out": row.check_out.isoformat(),
        "block_ref": row.block_ref,
        "reservation_id": row.reservation_id,
        "can_unblock": row.reservation_id is None,
        "source": "stay",
    }


def list_calendar_blocks(
    tenant: Tenant,
    *,
    date_from: date,
    date_to: date,
) -> list[dict]:
    rows = UnitAvailabilityBlock.objects.filter(
        tenant=tenant,
        check_out__gt=date_from,
        check_in__lt=date_to,
    ).select_related("unit").order_by("check_in", "unit__code")
    return [_serialize_block(row) for row in rows]


def validate_block_request(
    tenant: Tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
) -> None:
    if check_out <= check_in:
        raise CalendarBlockError("check_out must be after check_in")

    active_statuses = [
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    ]
    reservation_conflict = (
        Reservation.objects.for_tenant(tenant)
        .filter(
            units__unit_id=unit.id,
            status__in=active_statuses,
            check_out__gt=check_in,
            check_in__lt=check_out,
        )
        .exists()
    )
    if reservation_conflict:
        raise CalendarBlockError("Unit has an active reservation in the selected range.")

    block_conflict = UnitAvailabilityBlock.objects.filter(
        tenant=tenant,
        unit=unit,
        check_out__gt=check_in,
        check_in__lt=check_out,
    ).exists()
    if block_conflict:
        raise CalendarBlockError("Unit is already blocked in the selected range.")
