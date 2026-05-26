from __future__ import annotations

import uuid
from datetime import date

from django.db import transaction

from apps.integrations.channel_manager.resolver import get_channel_manager
from apps.integrations.models import UnitAvailabilityBlock
from apps.properties.models import Unit
from apps.reservations.booking_lifecycle import confirm_web_booking, is_web_pending_booking
from apps.reservations.models import Reservation
from apps.tenants.models import ChannelManager, Tenant


def sync_reservation_outbound(reservation: Reservation, *, action: str = "sync") -> dict:
    manager = get_channel_manager(reservation.tenant)
    if manager == ChannelManager.CHANNEX:
        from apps.integrations.channex.reservation_availability_service import (
            remove_reservation_channex_availability,
            sync_reservation_channex_availability,
        )

        if action == "remove":
            return remove_reservation_channex_availability(reservation)
        return sync_reservation_channex_availability(reservation)
    return {"skipped": True, "reason": "channel_manager_none", "reservation_id": reservation.pk}


def remove_reservation_outbound(reservation: Reservation) -> dict:
    return sync_reservation_outbound(reservation, action="remove")


def confirm_web_booking_if_ready(reservation_id: int, sync_result: dict) -> bool:
    reservation = Reservation.objects.filter(pk=reservation_id).first()
    if reservation is None or not is_web_pending_booking(reservation):
        return False

    manager = get_channel_manager(reservation.tenant)
    if manager == ChannelManager.NONE:
        return False

    if sync_result.get("skipped") or sync_result.get("refused"):
        return False

    if manager == ChannelManager.CHANNEX:
        if not sync_result.get("pushed"):
            return False

    return confirm_web_booking(reservation_id)


def _create_local_block(
    tenant: Tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
    *,
    reservation: Reservation | None = None,
    guest_label: str = "Block",
    notice: str = "",
) -> dict:
    block_ref = f"local:{uuid.uuid4().hex}"
    block_row = UnitAvailabilityBlock.objects.create(
        tenant=tenant,
        unit=unit,
        reservation=reservation,
        check_in=check_in,
        check_out=check_out,
        block_ref=block_ref,
        created_via=UnitAvailabilityBlock.CreatedVia.STAY,
    )
    return {
        "id": block_row.id,
        "block_ref": block_ref,
        "unit_code": unit.code,
        "unit_id": unit.id,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "notice": notice or f"stay.hr block {unit.code} {check_in}..{check_out}",
        "guest_label": guest_label,
    }


def create_calendar_block(
    tenant: Tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
    *,
    guest_label: str = "Block",
    notice: str = "",
) -> dict:
    manager = get_channel_manager(tenant)

    with transaction.atomic():
        result = _create_local_block(
            tenant,
            unit,
            check_in,
            check_out,
            guest_label=guest_label,
            notice=notice,
        )
        if manager == ChannelManager.CHANNEX:
            from apps.integrations.channex.ari_service import push_channex_ari
            from apps.integrations.channex.reservation_availability_service import (
                get_active_channex_integration,
                push_availability_range_for_unit,
            )

            integration = get_active_channex_integration(tenant.slug)
            push_availability_range_for_unit(
                tenant,
                unit,
                check_in,
                check_out,
            )
            push_channex_ari(integration)
            result["channex_pushed"] = True
    return result


def delete_calendar_block(block_row: UnitAvailabilityBlock) -> None:
    tenant = block_row.tenant
    manager = get_channel_manager(tenant)
    unit = block_row.unit
    check_in = block_row.check_in
    check_out = block_row.check_out

    block_row.delete()
    if manager == ChannelManager.CHANNEX and unit is not None:
        from apps.integrations.channex.ari_service import push_channex_ari
        from apps.integrations.channex.reservation_availability_service import (
            get_active_channex_integration,
            push_availability_range_for_unit,
        )

        integration = get_active_channex_integration(tenant.slug)
        push_availability_range_for_unit(tenant, unit, check_in, check_out)
        push_channex_ari(integration)
