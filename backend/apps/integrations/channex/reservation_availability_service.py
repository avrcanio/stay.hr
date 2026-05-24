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
