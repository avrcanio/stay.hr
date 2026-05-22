from __future__ import annotations

from datetime import date
from typing import Any

from django.core.cache import cache
from apps.integrations.models import IntegrationConfig, UnitAvailabilityBlock
from apps.integrations.smoobu.blocking_service import SMOOBU_BLOCKED_CHANNEL_ID
from apps.integrations.smoobu.booking_service import _booking_field, _parse_date
from apps.integrations.smoobu.client import SmoobuClient
from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuApiError, SmoobuConfigError, SmoobuRatesError
from apps.integrations.smoobu.resolver import get_active_smoobu_integration
from apps.properties.models import Unit
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

EXTERNAL_BLOCKS_CACHE_SECONDS = 60


def _ranges_overlap(
    a_start: date,
    a_end: date,
    b_start: date,
    b_end: date,
) -> bool:
    return a_start < b_end and a_end > b_start


def _is_blocked_smoobu_booking(booking: dict[str, Any]) -> bool:
    if _booking_field(booking, "is-blocked-booking", "is_blocked_booking") is True:
        return True
    channel = _booking_field(booking, "channel") or {}
    if isinstance(channel, dict):
        channel_id = channel.get("id")
        if channel_id is not None and int(channel_id) == SMOOBU_BLOCKED_CHANNEL_ID:
            return True
    booking_type = str(_booking_field(booking, "type") or "").strip().lower()
    return booking_type in {"blocked", "block", "blocked-booking"}


def _booking_is_cancelled(booking: dict[str, Any]) -> bool:
    booking_type = str(_booking_field(booking, "type") or "").strip().lower()
    if booking_type in {"cancellation", "cancelled", "canceled", "cancel"}:
        return True
    for key in ("status", "booking-status", "booking_status"):
        raw = str(_booking_field(booking, key) or "").strip().lower()
        if raw in {"cancelled", "canceled", "cancel", "cancellation"}:
            return True
    return False


def _serialize_hospira_block(row: UnitAvailabilityBlock) -> dict[str, Any]:
    return {
        "id": row.id,
        "unit_id": row.unit_id,
        "unit_code": row.unit.code,
        "check_in": row.check_in.isoformat(),
        "check_out": row.check_out.isoformat(),
        "smoobu_booking_id": row.smoobu_booking_id,
        "can_unblock": True,
        "source": "hospira",
    }


def _serialize_external_block(
    *,
    unit: Unit,
    check_in: date,
    check_out: date,
    smoobu_booking_id: str,
) -> dict[str, Any]:
    return {
        "id": None,
        "unit_id": unit.id,
        "unit_code": unit.code,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "smoobu_booking_id": smoobu_booking_id,
        "can_unblock": False,
        "source": "smoobu",
    }


def _fetch_external_blocks(
    integration_row: IntegrationConfig,
    *,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    cache_key = (
        f"smoobu_external_blocks:{integration_row.tenant_id}:"
        f"{date_from.isoformat()}:{date_to.isoformat()}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    config = SmoobuRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    hospira_ids = set(
        UnitAvailabilityBlock.objects.filter(
            tenant=integration_row.tenant,
            check_out__gt=date_from,
            check_in__lt=date_to,
        ).values_list("smoobu_booking_id", flat=True)
    )

    results: list[dict[str, Any]] = []
    client = SmoobuClient(config)
    try:
        for link in config.apartments:
            unit = None
            if link.unit_id:
                unit = Unit.objects.filter(
                    tenant=integration_row.tenant,
                    id=link.unit_id,
                ).first()
            if unit is None:
                unit = Unit.objects.filter(
                    tenant=integration_row.tenant,
                    code=link.unit_code,
                ).first()
            if unit is None:
                continue

            bookings = client.iter_reservations(
                date_from=date_from,
                date_to=date_to,
                apartment_id=link.smoobu_apartment_id,
                exclude_blocked=False,
            )
            for booking in bookings:
                if not _is_blocked_smoobu_booking(booking):
                    continue
                if _booking_is_cancelled(booking):
                    continue
                booking_id = _booking_field(booking, "id")
                if booking_id is None:
                    continue
                smoobu_id = str(booking_id)
                if smoobu_id in hospira_ids:
                    continue

                check_in = _parse_date(_booking_field(booking, "arrival"))
                check_out = _parse_date(_booking_field(booking, "departure"))
                if check_in is None or check_out is None:
                    continue
                if not _ranges_overlap(check_in, check_out, date_from, date_to):
                    continue

                results.append(
                    _serialize_external_block(
                        unit=unit,
                        check_in=check_in,
                        check_out=check_out,
                        smoobu_booking_id=smoobu_id,
                    )
                )
    except SmoobuApiError:
        results = []
    finally:
        client.close()

    cache.set(cache_key, results, EXTERNAL_BLOCKS_CACHE_SECONDS)
    return results


def list_calendar_blocks(
    tenant: Tenant,
    *,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    hospira_rows = UnitAvailabilityBlock.objects.filter(
        tenant=tenant,
        check_out__gt=date_from,
        check_in__lt=date_to,
    ).select_related("unit").order_by("check_in", "unit__code")

    blocks = [_serialize_hospira_block(row) for row in hospira_rows]

    try:
        integration = get_active_smoobu_integration(tenant.slug)
    except SmoobuConfigError:
        return blocks

    blocks.extend(
        _fetch_external_blocks(
            integration,
            date_from=date_from,
            date_to=date_to,
        )
    )
    blocks.sort(key=lambda item: (item["check_in"], item["unit_code"]))
    return blocks


def validate_block_request(
    tenant: Tenant,
    unit: Unit,
    check_in: date,
    check_out: date,
) -> None:
    if check_out <= check_in:
        raise SmoobuRatesError("check_out must be after check_in")

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
        raise SmoobuRatesError("Unit has an active reservation in the selected range.")

    block_conflict = UnitAvailabilityBlock.objects.filter(
        tenant=tenant,
        unit=unit,
        check_out__gt=check_in,
        check_in__lt=check_out,
    ).exists()
    if block_conflict:
        raise SmoobuRatesError("Unit is already blocked in the selected range.")

    existing_blocks = list_calendar_blocks(tenant, date_from=check_in, date_to=check_out)
    for item in existing_blocks:
        if item["unit_id"] == unit.id and item.get("source") == "smoobu":
            raise SmoobuRatesError("Unit is already blocked in Smoobu for the selected range.")
