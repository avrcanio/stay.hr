from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.integrations.channex.ari_payload import (
    build_availability_value,
    build_restriction_value,
)
from apps.integrations.channex.booking_test import certification_property_slug
from apps.integrations.channex.client import ChannexClient
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.integrations.channex.resolver import resolve_channex_config
from apps.integrations.models import (
    ChannelRatePlan,
    ChannexAriOutbox,
    IntegrationConfig,
    RatePlanDay,
    UnitAvailabilityDay,
)
from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

FULL_SYNC_DAYS = 500


def certification_property(tenant: Tenant, config: ChannexRuntimeConfig) -> Property:
    slug = config.certification_property_slug or certification_property_slug(tenant.slug)
    try:
        return Property.objects.get(tenant=tenant, slug=slug)
    except Property.DoesNotExist as exc:
        raise ChannexBookingIngestError(f"Property '{slug}' not found.") from exc


def seed_channel_rate_plans_from_config(integration_row: IntegrationConfig) -> int:
    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    tenant = integration_row.tenant
    prop = certification_property(tenant, config)
    raw = integration_row.get_config_dict().get("booking_test_rooms") or []
    created = 0

    for room in raw:
        unit_code = str(room.get("unit_code") or "")
        unit = Unit.objects.filter(tenant=tenant, property=prop, code=unit_code).first()
        if unit is None:
            continue
        room_type_id = str(room.get("channex_room_type_id") or "")
        for rp in room.get("rate_plans") or []:
            code = str(rp.get("code") or "")
            if not code:
                continue
            _, was_created = ChannelRatePlan.objects.update_or_create(
                tenant=tenant,
                property=prop,
                unit=unit,
                code=code,
                defaults={
                    "title": str(rp.get("title") or code),
                    "channex_room_type_id": room_type_id,
                    "channex_rate_plan_id": str(rp.get("channex_rate_plan_id") or ""),
                    "default_rate": Decimal(str(rp.get("default_gbp") or "0")),
                    "currency": "GBP",
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
    return created


def enqueue_outbox_values(
    *,
    tenant: Tenant,
    property: Property,
    kind: str,
    values: list[dict[str, Any]],
) -> ChannexAriOutbox | None:
    if not values:
        return None

    pending = (
        ChannexAriOutbox.objects.filter(
            tenant=tenant,
            property=property,
            kind=kind,
            status=ChannexAriOutbox.Status.PENDING,
        )
        .order_by("-id")
        .first()
    )
    if pending is not None:
        pending.values = list(pending.values or []) + values
        pending.save(update_fields=["values", "updated_at"])
        return pending

    return ChannexAriOutbox.objects.create(
        tenant=tenant,
        property=property,
        kind=kind,
        values=values,
        status=ChannexAriOutbox.Status.PENDING,
    )


def _mark_availability_synced(unit_ids: set[int], dates: set[date]) -> None:
    if not unit_ids or not dates:
        return
    UnitAvailabilityDay.objects.filter(unit_id__in=unit_ids, date__in=dates).update(
        synced_at=timezone.now()
    )


def _mark_rates_synced(rate_plan_ids: set[int], dates: set[date]) -> None:
    if not rate_plan_ids or not dates:
        return
    RatePlanDay.objects.filter(rate_plan_id__in=rate_plan_ids, date__in=dates).update(
        synced_at=timezone.now()
    )


def flush_channex_ari_outbox(
    integration_row: IntegrationConfig,
    *,
    client: ChannexClient | None = None,
) -> list[dict[str, Any]]:
    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    tenant = integration_row.tenant
    prop = certification_property(tenant, config)
    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)

    results: list[dict[str, Any]] = []
    try:
        pending_rows = list(
            ChannexAriOutbox.objects.filter(
                tenant=tenant,
                property=prop,
                status=ChannexAriOutbox.Status.PENDING,
            ).order_by("kind", "id")
        )
        for row in pending_rows:
            try:
                if row.kind == ChannexAriOutbox.Kind.AVAILABILITY:
                    response = client.update_availability(list(row.values or []))
                else:
                    response = client.update_restrictions(list(row.values or []))
                task_ids = client.extract_task_ids(response)
                row.status = ChannexAriOutbox.Status.SENT
                row.channex_task_ids = task_ids
                row.sent_at = timezone.now()
                row.error_message = ""
                row.save(
                    update_fields=[
                        "status",
                        "channex_task_ids",
                        "sent_at",
                        "error_message",
                        "updated_at",
                    ]
                )
                results.append(
                    {
                        "outbox_id": row.id,
                        "kind": row.kind,
                        "task_ids": task_ids,
                        "values_count": len(row.values or []),
                    }
                )
                time.sleep(0.5)
            except Exception as exc:
                row.status = ChannexAriOutbox.Status.FAILED
                row.error_message = str(exc)[:2000]
                row.save(update_fields=["status", "error_message", "updated_at"])
                logger.exception("channex ari outbox flush failed", extra={"outbox_id": row.id})
                raise
    finally:
        if owns_client and client is not None:
            client.close()
    return results


@transaction.atomic
def apply_rate_updates(
    integration_row: IntegrationConfig,
    updates: list[dict[str, Any]],
    *,
    queue_push: bool = True,
) -> list[RatePlanDay]:
    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    tenant = integration_row.tenant
    prop = certification_property(tenant, config)
    property_id = config.property_id

    saved: list[RatePlanDay] = []
    outbox_values: list[dict[str, Any]] = []

    for item in updates:
        unit_code = str(item["unit_code"])
        rate_code = str(item["rate_plan_code"])
        rate_plan = ChannelRatePlan.objects.select_related("unit").get(
            tenant=tenant,
            property=prop,
            unit__code=unit_code,
            code=rate_code,
            is_active=True,
        )
        day, day_to = _resolve_date_range(item)
        defaults: dict[str, Any] = {"rate": Decimal(str(item["rate"]))}
        for field in (
            "min_stay_arrival",
            "min_stay_through",
            "max_stay",
            "stop_sell",
            "closed_to_arrival",
            "closed_to_departure",
        ):
            if field in item:
                defaults[field] = item[field]

        current = day
        while current <= day_to:
            row, _ = RatePlanDay.objects.update_or_create(
                tenant=tenant,
                rate_plan=rate_plan,
                date=current,
                defaults={**defaults, "synced_at": None},
            )
            saved.append(row)
            current += timedelta(days=1)

        sample = saved[-1]
        if day == day_to:
            outbox_values.append(
                build_restriction_value(
                    property_id=property_id,
                    rate_plan_id=rate_plan.channex_rate_plan_id,
                    day=day.isoformat(),
                    rate=sample.rate,
                    min_stay_arrival=sample.min_stay_arrival,
                    min_stay_through=sample.min_stay_through,
                    max_stay=sample.max_stay,
                    stop_sell=sample.stop_sell,
                    closed_to_arrival=sample.closed_to_arrival,
                    closed_to_departure=sample.closed_to_departure,
                )
            )
        else:
            outbox_values.append(
                build_restriction_value(
                    property_id=property_id,
                    rate_plan_id=rate_plan.channex_rate_plan_id,
                    date_from=day.isoformat(),
                    date_to=day_to.isoformat(),
                    rate=sample.rate,
                    min_stay_arrival=sample.min_stay_arrival,
                    min_stay_through=sample.min_stay_through,
                    max_stay=sample.max_stay,
                    stop_sell=sample.stop_sell,
                    closed_to_arrival=sample.closed_to_arrival,
                    closed_to_departure=sample.closed_to_departure,
                )
            )

    if queue_push and outbox_values:
        enqueue_outbox_values(
            tenant=tenant,
            property=prop,
            kind=ChannexAriOutbox.Kind.RESTRICTIONS,
            values=outbox_values,
        )
    return saved


@transaction.atomic
def apply_availability_updates(
    integration_row: IntegrationConfig,
    updates: list[dict[str, Any]],
    *,
    queue_push: bool = True,
) -> list[UnitAvailabilityDay]:
    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    tenant = integration_row.tenant
    prop = certification_property(tenant, config)
    property_id = config.property_id

    saved: list[UnitAvailabilityDay] = []
    outbox_values: list[dict[str, Any]] = []

    for item in updates:
        unit = Unit.objects.get(tenant=tenant, property=prop, code=str(item["unit_code"]))
        room_type_id = _room_type_id_for_unit(integration_row, unit)
        day, day_to = _resolve_date_range(item)
        availability = int(item["availability"])
        current = day
        while current <= day_to:
            row, _ = UnitAvailabilityDay.objects.update_or_create(
                tenant=tenant,
                unit=unit,
                date=current,
                defaults={"availability": availability, "synced_at": None},
            )
            saved.append(row)
            current += timedelta(days=1)

        if day == day_to:
            outbox_values.append(
                build_availability_value(
                    property_id=property_id,
                    room_type_id=room_type_id,
                    availability=availability,
                    day=day.isoformat(),
                )
            )
        else:
            outbox_values.append(
                build_availability_value(
                    property_id=property_id,
                    room_type_id=room_type_id,
                    availability=availability,
                    date_from=day.isoformat(),
                    date_to=day_to.isoformat(),
                )
            )

    if queue_push and outbox_values:
        enqueue_outbox_values(
            tenant=tenant,
            property=prop,
            kind=ChannexAriOutbox.Kind.AVAILABILITY,
            values=outbox_values,
        )
    return saved


def _room_type_id_for_unit(integration_row: IntegrationConfig, unit: Unit) -> str:
    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    for room in integration_row.get_config_dict().get("booking_test_rooms") or []:
        if str(room.get("unit_code")) == unit.code:
            room_type_id = str(room.get("channex_room_type_id") or "")
            if room_type_id:
                return room_type_id
    for link in config.booking_test_rooms:
        if link.unit_id == unit.id:
            return link.channex_room_type_id
    raise ChannexBookingIngestError(f"No Channex room type mapping for unit {unit.code}")


def _resolve_date_range(item: dict[str, Any]) -> tuple[date, date]:
    if item.get("date"):
        day = date.fromisoformat(str(item["date"]))
        return day, day
    day_from = date.fromisoformat(str(item["date_from"]))
    day_to = date.fromisoformat(str(item["date_to"]))
    if day_to < day_from:
        raise ChannexBookingIngestError("date_to must be on or after date_from")
    return day_from, day_to


def _generated_rate(base: Decimal, day: date, plan_code: str) -> Decimal:
    weekday = day.weekday()
    bump = Decimal(weekday >= 5) * Decimal("15")
    month_bump = Decimal((day.month % 3) * 7)
    plan_bump = Decimal("10") if plan_code == "non_refundable" else Decimal("0")
    return base + bump + month_bump + plan_bump


def _generated_availability(unit_code: str, day: date) -> int:
    if unit_code == "BCOM-HOLIDAY":
        return 1
    if day.weekday() >= 5:
        return 0
    return 1


@transaction.atomic
def build_full_sync(
    integration_row: IntegrationConfig,
    *,
    days: int = FULL_SYNC_DAYS,
    start: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    tenant = integration_row.tenant
    prop = certification_property(tenant, config)
    property_id = config.property_id
    start_day = start or timezone.localdate()
    end_day = start_day + timedelta(days=days - 1)

    availability_values: list[dict[str, Any]] = []
    restriction_values: list[dict[str, Any]] = []

    units = Unit.objects.filter(tenant=tenant, property=prop, is_active=True)
    rate_plans = ChannelRatePlan.objects.filter(
        tenant=tenant, property=prop, is_active=True
    ).select_related("unit")

    current = start_day
    while current <= end_day:
        for unit in units:
            availability = _generated_availability(unit.code, current)
            UnitAvailabilityDay.objects.update_or_create(
                tenant=tenant,
                unit=unit,
                date=current,
                defaults={"availability": availability, "synced_at": None},
            )
        for plan in rate_plans:
            rate = _generated_rate(plan.default_rate, current, plan.code)
            RatePlanDay.objects.update_or_create(
                tenant=tenant,
                rate_plan=plan,
                date=current,
                defaults={
                    "rate": rate,
                    "min_stay_arrival": 1,
                    "stop_sell": False,
                    "closed_to_arrival": False,
                    "closed_to_departure": False,
                    "synced_at": None,
                },
            )
        current += timedelta(days=1)

    for unit in units:
        room_type_id = _room_type_id_for_unit(integration_row, unit)
        availability_values.append(
            build_availability_value(
                property_id=property_id,
                room_type_id=room_type_id,
                availability=1,
                date_from=start_day.isoformat(),
                date_to=end_day.isoformat(),
            )
        )
        if unit.code == "BCOM-STUDIO":
            availability_values.append(
                {
                    **build_availability_value(
                        property_id=property_id,
                        room_type_id=room_type_id,
                        availability=0,
                        date_from=start_day.isoformat(),
                        date_to=end_day.isoformat(),
                    ),
                    "days": ["sa", "su"],
                }
            )

    month_cursor = start_day.replace(day=1)
    while month_cursor <= end_day:
        month_end = (month_cursor.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        range_from = max(start_day, month_cursor)
        range_to = min(end_day, month_end)
        if range_from <= range_to:
            sample_day = range_from + timedelta(days=(range_to - range_from).days // 2)
            for plan in rate_plans:
                restriction_values.append(
                    build_restriction_value(
                        property_id=property_id,
                        rate_plan_id=plan.channex_rate_plan_id,
                        date_from=range_from.isoformat(),
                        date_to=range_to.isoformat(),
                        rate=_generated_rate(plan.default_rate, sample_day, plan.code),
                        min_stay_arrival=1 + (sample_day.month % 3),
                    )
                )
        if month_cursor.month == 12:
            month_cursor = month_cursor.replace(year=month_cursor.year + 1, month=1)
        else:
            month_cursor = month_cursor.replace(month=month_cursor.month + 1)

    enqueue_outbox_values(
        tenant=tenant,
        property=prop,
        kind=ChannexAriOutbox.Kind.AVAILABILITY,
        values=availability_values,
    )
    enqueue_outbox_values(
        tenant=tenant,
        property=prop,
        kind=ChannexAriOutbox.Kind.RESTRICTIONS,
        values=restriction_values,
    )
    return availability_values, restriction_values


def push_channex_ari(
    integration_row: IntegrationConfig,
    *,
    flush: bool = True,
) -> list[dict[str, Any]]:
    if flush:
        return flush_channex_ari_outbox(integration_row)
    return []


def get_active_channex_integration(tenant_slug: str = "demo") -> IntegrationConfig:
    row = (
        IntegrationConfig.objects.filter(
            tenant__slug=tenant_slug,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        .select_related("tenant")
        .first()
    )
    if row is None:
        raise ChannexBookingIngestError(f"No Channex config for tenant {tenant_slug}")
    return row
