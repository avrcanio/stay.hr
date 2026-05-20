from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.integrations.models import IntegrationConfig, UnitRateDay
from apps.integrations.smoobu.client import SmoobuClient
from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuRatesError
from apps.properties.models import Unit

logger = logging.getLogger(__name__)


def _parse_day(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _resolve_date_range(item: dict[str, Any]) -> tuple[date, date]:
    if item.get("date"):
        day = _parse_day(item["date"])
        return day, day
    day_from = _parse_day(item["date_from"])
    day_to = _parse_day(item["date_to"])
    if day_to < day_from:
        raise SmoobuRatesError("date_to must be on or after date_from")
    return day_from, day_to


def _resolve_min_stay(item: dict[str, Any]) -> int | None:
    if "min_stay" in item and item["min_stay"] is not None:
        return int(item["min_stay"])
    if "min_stay_arrival" in item and item["min_stay_arrival"] is not None:
        return int(item["min_stay_arrival"])
    return None


def _format_operation_dates(day: date, day_to: date) -> list[str]:
    if day == day_to:
        return [day.isoformat()]
    return [f"{day.isoformat()}:{day_to.isoformat()}"]


def build_rate_operation(
    *,
    day: date,
    day_to: date,
    rate: Decimal,
    min_stay: int | None,
    available: int = 1,
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "dates": _format_operation_dates(day, day_to),
        "daily_price": float(rate),
        "available": available,
    }
    if min_stay is not None:
        operation["min_length_of_stay"] = min_stay
    return operation


def _apartment_id_for_unit(config: SmoobuRuntimeConfig, unit: Unit) -> int:
    apartment_id = config.apartment_id_for_unit_code(unit.code)
    if apartment_id is None:
        raise SmoobuRatesError(f"No Smoobu apartment mapping for unit {unit.code}")
    return apartment_id


@transaction.atomic
def apply_rate_updates(
    integration_row: IntegrationConfig,
    updates: list[dict[str, Any]],
    *,
    push: bool = True,
) -> tuple[list[UnitRateDay], list[dict[str, Any]]]:
    config = SmoobuRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    tenant = integration_row.tenant

    saved: list[UnitRateDay] = []
    push_batches: dict[int, list[dict[str, Any]]] = {}

    for item in updates:
        unit = Unit.objects.get(tenant=tenant, code=str(item["unit_code"]))
        day, day_to = _resolve_date_range(item)
        rate = Decimal(str(item["rate"]))
        min_stay = _resolve_min_stay(item)
        apartment_id = _apartment_id_for_unit(config, unit)

        current = day
        while current <= day_to:
            row, _ = UnitRateDay.objects.update_or_create(
                tenant=tenant,
                unit=unit,
                date=current,
                defaults={
                    "rate": rate,
                    "min_stay": min_stay,
                    "smoobu_synced_at": None,
                },
            )
            saved.append(row)
            current += timedelta(days=1)

        push_batches.setdefault(apartment_id, []).append(
            build_rate_operation(day=day, day_to=day_to, rate=rate, min_stay=min_stay)
        )

    push_results: list[dict[str, Any]] = []
    if push and config.push_rates_enabled and push_batches:
        push_results = _push_rate_batches(config, push_batches, saved)

    return saved, push_results


def push_smoobu_rates(
    integration_row: IntegrationConfig,
    *,
    client: SmoobuClient | None = None,
) -> list[dict[str, Any]]:
    config = SmoobuRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    if not config.push_rates_enabled:
        return []

    tenant = integration_row.tenant
    unsynced = list(
        UnitRateDay.objects.filter(tenant=tenant, smoobu_synced_at__isnull=True)
        .select_related("unit")
        .order_by("unit_id", "date")
    )
    if not unsynced:
        return []

    push_batches: dict[int, list[dict[str, Any]]] = {}
    for row in unsynced:
        apartment_id = _apartment_id_for_unit(config, row.unit)
        push_batches.setdefault(apartment_id, []).append(
            build_rate_operation(
                day=row.date,
                day_to=row.date,
                rate=row.rate,
                min_stay=row.min_stay,
            )
        )

    return _push_rate_batches(config, push_batches, unsynced, client=client)


def _push_rate_batches(
    config: SmoobuRuntimeConfig,
    push_batches: dict[int, list[dict[str, Any]]],
    rows_to_mark: list[UnitRateDay],
    *,
    client: SmoobuClient | None = None,
) -> list[dict[str, Any]]:
    owns_client = client is None
    if owns_client:
        client = SmoobuClient(config)

    results: list[dict[str, Any]] = []
    synced_at = timezone.now()
    try:
        for apartment_id, operations in push_batches.items():
            response = client.post_rates(
                apartment_ids=[apartment_id],
                operations=operations,
            )
            if response.get("success") is not True:
                raise SmoobuRatesError(
                    f"Smoobu POST /api/rates failed for apartment {apartment_id}: {response}"
                )
            results.append(
                {
                    "apartment_id": apartment_id,
                    "operations_count": len(operations),
                    "success": True,
                }
            )

        row_ids = [row.id for row in rows_to_mark]
        UnitRateDay.objects.filter(id__in=row_ids).update(smoobu_synced_at=synced_at)
    finally:
        if owns_client and client is not None:
            client.close()

    return results
