"""Compare stay.hr occupancy vs live Channex availability; re-push on mismatch.

Platform-wide: callers pass ``tenant_slug`` (any Channex tenant). Ops defaults
(tenant 2 / uzorita) live only in Celery beat kwargs, CLI, and daily-ops settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.utils import timezone

from apps.integrations.channex.ari_service import (
    apply_availability_updates,
    get_active_channex_integration,
    push_channex_ari,
    sync_property,
)
from apps.integrations.channex.client import ChannexClient
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import (
    ChannexApiError,
    ChannexBookingIngestError,
)
from apps.integrations.channex.reservation_availability_service import (
    compute_unit_availability,
)
from apps.properties.models import Unit
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

DEFAULT_VERIFY_DAYS = 90


@dataclass(frozen=True)
class AvailabilityMismatch:
    unit_code: str
    room_type_id: str
    day: date
    expected: int
    actual: int


def _room_type_id_for_unit(integration, config: ChannexRuntimeConfig, unit: Unit) -> str | None:
    room_type_id = config.room_type_id_for_unit_code(unit.code)
    if room_type_id:
        return room_type_id
    for room in integration.get_config_dict().get("booking_test_rooms") or []:
        if str(room.get("unit_code")) == unit.code:
            room_type_id = str(room.get("channex_room_type_id") or "")
            if room_type_id:
                return room_type_id
    for link in config.booking_test_rooms:
        if link.unit_id == unit.id and link.channex_room_type_id:
            return link.channex_room_type_id
    return None


def _mapped_units(
    integration,
    config: ChannexRuntimeConfig,
) -> list[tuple[Unit, str]]:
    """Return (unit, channex_room_type_id) for units with a Channex mapping."""
    tenant = integration.tenant
    prop = sync_property(tenant, config)
    units = list(Unit.objects.filter(tenant=tenant, property=prop, is_active=True))
    mapped: list[tuple[Unit, str]] = []
    for unit in units:
        room_type_id = _room_type_id_for_unit(integration, config, unit)
        if room_type_id:
            mapped.append((unit, room_type_id))
    return mapped


def _parse_live_availability(
    live: dict[str, Any],
    room_type_id: str,
    day: date,
) -> int | None:
    """Return Channex availability for room_type/day, or None if missing."""
    by_room = live.get(room_type_id)
    if not isinstance(by_room, dict):
        return None
    raw = by_room.get(day.isoformat())
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def find_availability_mismatches(
    *,
    tenant_slug: str,
    days: int = DEFAULT_VERIFY_DAYS,
    from_date: date | None = None,
    client: ChannexClient | None = None,
) -> tuple[list[AvailabilityMismatch], dict[str, Any]]:
    """Compare expected stay.hr availability against live Channex GET /availability."""
    if not (tenant_slug or "").strip():
        raise ValueError("tenant_slug is required")

    integration = get_active_channex_integration(tenant_slug)
    config = ChannexRuntimeConfig.from_integration_dict(integration.get_config_dict())
    if not config.property_id:
        raise ChannexBookingIngestError("Channex property_id missing")

    start = from_date or timezone.localdate()
    end = start + timedelta(days=max(1, days) - 1)
    mapped = _mapped_units(integration, config)
    if not mapped:
        return [], {
            "tenant_slug": tenant_slug,
            "property_id": config.property_id,
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "units_checked": 0,
            "skipped": True,
            "reason": "no_mapped_units",
        }

    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)
    try:
        live = client.get_availability(
            property_id=config.property_id,
            date_from=start.isoformat(),
            date_to=end.isoformat(),
        )
    finally:
        if owns_client:
            client.close()

    mismatches: list[AvailabilityMismatch] = []
    current = start
    while current <= end:
        for unit, room_type_id in mapped:
            expected = compute_unit_availability(integration.tenant, unit, current)
            actual = _parse_live_availability(live, room_type_id, current)
            if actual is None:
                # Missing day in Channex response — treat as mismatch vs expected.
                actual = -1
            if actual != expected:
                mismatches.append(
                    AvailabilityMismatch(
                        unit_code=unit.code,
                        room_type_id=room_type_id,
                        day=current,
                        expected=expected,
                        actual=actual,
                    )
                )
        current += timedelta(days=1)

    meta = {
        "tenant_slug": tenant_slug,
        "tenant_id": integration.tenant_id,
        "property_id": config.property_id,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "units_checked": len(mapped),
        "mismatch_count": len(mismatches),
    }
    return mismatches, meta


def _repair_mismatches(integration, mismatches: list[AvailabilityMismatch]) -> int:
    if not mismatches:
        return 0
    updates = [
        {
            "unit_code": row.unit_code,
            "date": row.day.isoformat(),
            "availability": row.expected,
        }
        for row in mismatches
        if row.expected >= 0
    ]
    if not updates:
        return 0
    apply_availability_updates(integration, updates, queue_push=True)
    push_channex_ari(integration)
    return len(updates)


def _notify_mismatches(tenant: Tenant, mismatches: list[AvailabilityMismatch]) -> None:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data

    lines = [
        f"{m.unit_code} {m.day.isoformat()}: expected={m.expected} channex={m.actual}"
        for m in mismatches[:5]
    ]
    if len(mismatches) > 5:
        lines.append(f"+{len(mismatches) - 5} još")
    body = "; ".join(lines)
    data = reception_push_data(
        event_type="channel.ari_mismatch",
        reservation_id=0,
        summary=body,
        tenant_id=str(tenant.pk),
        mismatch_count=str(len(mismatches)),
    )
    send_tenant_reception_push(
        tenant_id=tenant.pk,
        title=f"Channex ARI mismatch ({len(mismatches)})",
        body=body,
        data=data,
    )


def verify_and_repair_availability(
    *,
    tenant_slug: str,
    days: int = DEFAULT_VERIFY_DAYS,
    from_date: date | None = None,
    repair: bool = True,
    notify: bool = True,
    client: ChannexClient | None = None,
) -> dict[str, Any]:
    """Verify live Channex availability; optionally re-push and alert on mismatch."""
    try:
        mismatches, meta = find_availability_mismatches(
            tenant_slug=tenant_slug,
            days=days,
            from_date=from_date,
            client=client,
        )
    except (ChannexBookingIngestError, ChannexApiError, ValueError) as exc:
        logger.warning(
            "channex availability verify failed: %s",
            exc,
            extra={"tenant_slug": tenant_slug},
        )
        return {
            "skipped": True,
            "reason": str(exc),
            "tenant_slug": tenant_slug,
            "mismatch_count": None,
            "repaired": 0,
        }

    repaired = 0
    if repair and mismatches:
        integration = get_active_channex_integration(tenant_slug)
        repaired = _repair_mismatches(integration, mismatches)
        logger.warning(
            "channex availability mismatches repaired",
            extra={
                "tenant_slug": tenant_slug,
                "mismatch_count": len(mismatches),
                "repaired": repaired,
            },
        )
    elif mismatches:
        logger.warning(
            "channex availability mismatches detected",
            extra={"tenant_slug": tenant_slug, "mismatch_count": len(mismatches)},
        )

    if notify and mismatches:
        tenant = Tenant.objects.filter(slug=tenant_slug).first()
        if tenant is not None:
            _notify_mismatches(tenant, mismatches)

    return {
        **meta,
        "mismatch_count": len(mismatches),
        "repaired": repaired,
        "mismatches": [
            {
                "unit_code": m.unit_code,
                "day": m.day.isoformat(),
                "expected": m.expected,
                "actual": m.actual,
            }
            for m in mismatches[:50]
        ],
    }
