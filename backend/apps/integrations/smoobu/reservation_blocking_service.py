from __future__ import annotations

import logging

from apps.integrations.models import UnitAvailabilityBlock
from apps.integrations.smoobu.blocking_service import block_apartment_dates, unblock_apartment_dates
from apps.integrations.smoobu.exceptions import SmoobuConfigError, SmoobuRatesError
from apps.integrations.smoobu.resolver import get_active_smoobu_integration
from apps.reservations.channel_sync import (
    IMPORT_SOURCE_BOOKING_PDF,
    IMPORT_SOURCE_BOOKING_XLS,
    IMPORT_SOURCE_SMOOBU,
)
from apps.reservations.models import Reservation, ReservationUnit

logger = logging.getLogger(__name__)

SYNC_BLOCK_STATUSES = frozenset(
    {
        Reservation.Status.PENDING,
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)

CHANNEL_IMPORT_SOURCES = frozenset(
    {
        IMPORT_SOURCE_SMOOBU,
        IMPORT_SOURCE_BOOKING_XLS,
        IMPORT_SOURCE_BOOKING_PDF,
    }
)


def should_sync_smoobu_block(reservation: Reservation) -> bool:
    if reservation.status not in SYNC_BLOCK_STATUSES:
        return False
    if reservation.import_source in CHANNEL_IMPORT_SOURCES:
        return False
    try:
        integration = get_active_smoobu_integration(reservation.tenant.slug)
    except SmoobuConfigError:
        return False

    config = integration.get_config_dict()
    apartments = {item.get("unit_code", "").upper() for item in config.get("apartments", [])}
    unit_codes = (
        ReservationUnit.objects.filter(reservation=reservation)
        .select_related("unit")
        .values_list("unit__code", flat=True)
    )
    for unit_code in unit_codes:
        if not unit_code or unit_code.upper() not in apartments:
            return False
    return True


def sync_reservation_smoobu_blocks(reservation: Reservation) -> dict:
    if not should_sync_smoobu_block(reservation):
        return {"skipped": True, "reason": "should_not_sync", "reservation_id": reservation.pk}

    integration = get_active_smoobu_integration(reservation.tenant.slug)
    created: list[dict] = []
    skipped: list[str] = []

    for row in ReservationUnit.objects.filter(reservation=reservation).select_related("unit"):
        if row.unit is None:
            continue

        existing = UnitAvailabilityBlock.objects.filter(
            tenant=reservation.tenant,
            reservation=reservation,
            unit=row.unit,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
        ).exists()
        if existing:
            skipped.append(row.unit.code)
            continue

        try:
            result = block_apartment_dates(
                integration,
                unit_code=row.unit.code,
                check_in=reservation.check_in,
                check_out=reservation.check_out,
                guest_label=(reservation.booker_name or "Block")[:64],
                notice=f"stay.hr #{reservation.pk}",
                reservation=reservation,
            )
        except SmoobuRatesError as exc:
            logger.warning(
                "smoobu reservation block failed",
                extra={
                    "reservation_id": reservation.pk,
                    "unit_code": row.unit.code,
                    "error": str(exc),
                },
            )
            raise

        created.append(result)
        logger.info(
            "smoobu reservation block created",
            extra={
                "reservation_id": reservation.pk,
                "unit_code": row.unit.code,
                "smoobu_booking_id": result["smoobu_booking_id"],
            },
        )

    return {
        "reservation_id": reservation.pk,
        "created": created,
        "skipped_units": skipped,
    }


def remove_reservation_smoobu_blocks(reservation: Reservation) -> dict:
    blocks = list(
        UnitAvailabilityBlock.objects.filter(
            tenant=reservation.tenant,
            reservation=reservation,
            created_via=UnitAvailabilityBlock.CreatedVia.HOSPIRA,
        )
    )
    removed: list[str] = []
    for block_row in blocks:
        smoobu_booking_id = block_row.smoobu_booking_id
        unblock_apartment_dates(block_row)
        removed.append(smoobu_booking_id)
        logger.info(
            "smoobu reservation block removed",
            extra={
                "reservation_id": reservation.pk,
                "smoobu_booking_id": smoobu_booking_id,
            },
        )

    return {"reservation_id": reservation.pk, "removed": removed}
