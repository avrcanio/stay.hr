from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db import transaction

from apps.integrations.channex.ari_service import apply_availability_updates, get_active_channex_integration
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.integrations.channel_manager.resolver import get_channel_manager
from apps.integrations.models import UnitAvailabilityBlock
from apps.properties.models import Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import ChannelManager

logger = logging.getLogger(__name__)

IMPORT_SOURCE_CHANNEX = "channex"

# Uzorita: multi-room / whole-property bookings must close all B.com listings.
UZORITA_WHOLE_PROPERTY_UNIT_CODES = frozenset({"R1", "R2", "R3", "R6"})

SYNC_AVAILABILITY_STATUSES = frozenset(
    {
        Reservation.Status.PENDING,
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)


def should_sync_channex_availability(reservation: Reservation) -> bool:
    if get_channel_manager(reservation.tenant) != ChannelManager.CHANNEX:
        return False
    if reservation.import_source == IMPORT_SOURCE_CHANNEX:
        return False
    if reservation.status not in SYNC_AVAILABILITY_STATUSES:
        return False

    try:
        integration = get_active_channex_integration(reservation.tenant.slug)
    except ChannexBookingIngestError:
        return False

    config = integration.get_config_dict()
    mapped_codes = {
        str(row.get("unit_code") or "")
        for row in (config.get("room_types") or []) + (config.get("booking_test_rooms") or [])
        if row.get("unit_code")
    }
    if not mapped_codes:
        return False

    unit_codes = ReservationUnit.objects.filter(reservation=reservation).values_list(
        "unit__code", flat=True
    )
    return all(code and code in mapped_codes for code in unit_codes)


def compute_unit_availability(tenant, unit: Unit, day: date) -> int:
    """Availability for a single-unit room type on one night [day, day+1)."""
    base_count = 1
    night_end = day + timedelta(days=1)

    reservation_overlap = ReservationUnit.objects.filter(
        tenant=tenant,
        unit=unit,
        reservation__status__in=SYNC_AVAILABILITY_STATUSES,
        reservation__check_in__lt=night_end,
        reservation__check_out__gt=day,
    ).exists()
    if reservation_overlap:
        return max(0, base_count - 1)

    block_overlap = UnitAvailabilityBlock.objects.filter(
        tenant=tenant,
        unit=unit,
        check_in__lt=night_end,
        check_out__gt=day,
    ).exists()
    if block_overlap:
        return max(0, base_count - 1)

    return base_count


def _night_range(check_in: date, check_out: date) -> list[date]:
    nights: list[date] = []
    current = check_in
    while current < check_out:
        nights.append(current)
        current += timedelta(days=1)
    return nights


def push_availability_range_for_unit(
    tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
) -> dict:
    integration = get_active_channex_integration(tenant.slug)
    updates = [
        {
            "unit_code": unit.code,
            "date": night.isoformat(),
            "availability": compute_unit_availability(tenant, unit, night),
        }
        for night in _night_range(check_in, check_out)
    ]
    if not updates:
        return {"skipped": True, "reason": "empty_range", "unit_code": unit.code}

    apply_availability_updates(integration, updates, queue_push=True)
    return {"pushed": True, "unit_code": unit.code, "nights": len(updates)}


def _mapped_unit_codes_on_reservation(reservation: Reservation) -> set[str]:
    return {
        row.unit.code
        for row in ReservationUnit.objects.filter(reservation=reservation).select_related("unit")
        if row.unit_id and row.unit.code
    }


def qualifies_for_whole_property_sync(reservation: Reservation) -> bool:
    """True when 2+ uzorita core rooms are assigned (whole-object / multi-room)."""
    if reservation.property.slug != "uzorita":
        return False
    codes = _mapped_unit_codes_on_reservation(reservation)
    overlap = codes & UZORITA_WHOLE_PROPERTY_UNIT_CODES
    return len(overlap) >= 2 or (
        (reservation.units_count or 0) >= 2 and len(overlap) >= 1
    )


def maybe_push_whole_property_availability(
    reservation: Reservation,
    integration,
    *,
    results: list[dict],
) -> None:
    if not qualifies_for_whole_property_sync(reservation):
        return
    tenant = reservation.tenant
    pushed_codes = {r.get("unit_code") for r in results if r.get("unit_code")}
    for unit in Unit.objects.filter(
        tenant=tenant,
        property=reservation.property,
        code__in=UZORITA_WHOLE_PROPERTY_UNIT_CODES,
    ):
        if unit.code in pushed_codes:
            continue
        results.append(
            push_availability_range_for_unit(
                tenant,
                unit,
                reservation.check_in,
                reservation.check_out,
            )
        )


def push_reservation_channex_availability_unconditional(reservation: Reservation) -> dict:
    """
    Recompute and push ARI for all mapped units (and whole-property extras).

    Used after unit assignment changes regardless of import_source.
    """
    if get_channel_manager(reservation.tenant) != ChannelManager.CHANNEX:
        return {"skipped": True, "reason": "not_channex", "reservation_id": reservation.pk}

    if reservation.status in {Reservation.Status.CANCELED, Reservation.Status.NO_SHOW}:
        return remove_reservation_channex_availability(reservation)

    if reservation.status not in SYNC_AVAILABILITY_STATUSES:
        return {
            "skipped": True,
            "reason": "status_not_syncable",
            "reservation_id": reservation.pk,
        }

    try:
        integration = get_active_channex_integration(reservation.tenant.slug)
    except ChannexBookingIngestError as exc:
        return {"skipped": True, "reason": str(exc), "reservation_id": reservation.pk}

    unit_rows = list(
        ReservationUnit.objects.filter(reservation=reservation).select_related("unit")
    )
    if not unit_rows:
        return {"skipped": True, "reason": "no_units", "reservation_id": reservation.pk}

    results: list[dict] = []
    for row in unit_rows:
        if row.unit is None:
            results.append({"skipped": True, "reason": "unmapped_unit", "room_name": row.room_name})
            continue
        results.append(
            push_availability_range_for_unit(
                reservation.tenant,
                row.unit,
                reservation.check_in,
                reservation.check_out,
            )
        )

    maybe_push_whole_property_availability(reservation, integration, results=results)

    from apps.integrations.channex.ari_service import push_channex_ari

    push_channex_ari(integration)
    logger.info(
        "channex inventory pushed for reservation",
        extra={
            "reservation_id": reservation.pk,
            "status": reservation.status,
            "import_source": reservation.import_source,
            "units": len(results),
        },
    )
    return {"reservation_id": reservation.pk, "pushed": True, "units": results}


def push_channex_inventory_after_ingest(reservation_id: int) -> dict:
    """
    Recompute and push ARI to Channex after inbound booking ingest/cancel.

    Unlike manual/web outbound sync, this runs for import_source=channex so the
    channel calendar reflects stay.hr inventory including the new booking.
    """
    reservation = (
        Reservation.objects.filter(pk=reservation_id)
        .select_related("tenant", "property")
        .first()
    )
    if reservation is None:
        return {"skipped": True, "reason": "not_found", "reservation_id": reservation_id}

    return push_reservation_channex_availability_unconditional(reservation)


@transaction.atomic
def sync_reservation_channex_availability(reservation: Reservation) -> dict:
    if not should_sync_channex_availability(reservation):
        return {"skipped": True, "reason": "should_not_sync", "reservation_id": reservation.pk}

    integration = get_active_channex_integration(reservation.tenant.slug)
    results: list[dict] = []
    for row in ReservationUnit.objects.filter(reservation=reservation).select_related("unit"):
        if row.unit is None:
            continue
        result = push_availability_range_for_unit(
            reservation.tenant,
            row.unit,
            reservation.check_in,
            reservation.check_out,
        )
        results.append(result)

    from apps.integrations.channex.ari_service import push_channex_ari

    push_channex_ari(integration)
    return {
        "reservation_id": reservation.pk,
        "pushed": True,
        "units": results,
    }


def remove_reservation_channex_availability(reservation: Reservation) -> dict:
    if get_channel_manager(reservation.tenant) != ChannelManager.CHANNEX:
        return {"skipped": True, "reason": "not_channex", "reservation_id": reservation.pk}

    integration = get_active_channex_integration(reservation.tenant.slug)
    results: list[dict] = []
    for row in ReservationUnit.objects.filter(reservation=reservation).select_related("unit"):
        if row.unit is None:
            continue
        result = push_availability_range_for_unit(
            reservation.tenant,
            row.unit,
            reservation.check_in,
            reservation.check_out,
        )
        results.append(result)

    from apps.integrations.channex.ari_service import push_channex_ari

    push_channex_ari(integration)
    return {
        "reservation_id": reservation.pk,
        "pushed": True,
        "units": results,
    }


def sync_reservation_channex_availability_for_dates(
    reservation: Reservation,
    check_in: date,
    check_out: date,
) -> dict:
    """Push availability delta for a specific date range (e.g. after date change)."""
    if get_channel_manager(reservation.tenant) != ChannelManager.CHANNEX:
        return {"skipped": True, "reason": "not_channex", "reservation_id": reservation.pk}

    integration = get_active_channex_integration(reservation.tenant.slug)
    results: list[dict] = []
    for row in ReservationUnit.objects.filter(reservation=reservation).select_related("unit"):
        if row.unit is None:
            continue
        results.append(
            push_availability_range_for_unit(
                reservation.tenant,
                row.unit,
                check_in,
                check_out,
            )
        )

    from apps.integrations.channex.ari_service import push_channex_ari

    push_channex_ari(integration)
    return {"reservation_id": reservation.pk, "pushed": True, "units": results}
