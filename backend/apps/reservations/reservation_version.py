"""Reservation-scoped monotonic version counters for cheap UI sync polling."""

from __future__ import annotations

import logging

from django.db.models import F

from apps.reservations.models import ReservationVersion, ReservationVersionScope
from apps.reservations.reservation_version_event_bus import (
    get_event_bus_backend_name,
    get_reservation_version_event_bus,
    resolve_tenant_slug,
)

logger = logging.getLogger(__name__)


def publish_reservation_version_changed(
    reservation_id: int,
    scope: ReservationVersionScope,
    version: int,
) -> None:
    """Fan-out to SSE subscribers via the configured EventBus (ADR 0005)."""
    logger.debug(
        "publish reservation_version_changed reservation=%s scope=%s version=%s",
        reservation_id,
        scope,
        version,
    )
    bus = get_reservation_version_event_bus()
    # Avoid an extra DB hop for the default in-process bus (touch latency budget).
    tenant_slug = ""
    if get_event_bus_backend_name() == "redis":
        tenant_slug = resolve_tenant_slug(reservation_id)
    bus.publish(reservation_id, scope.value, version, tenant_slug)


def touch_reservation_version(
    reservation_id: int | None,
    scope: ReservationVersionScope,
    *,
    reason: str = "",
) -> None:
    if reservation_id is None:
        return

    old_version, new_version = _bump_version(reservation_id, scope)

    logger.info(
        "touch reservation_version reservation=%s scope=%s reason=%s old=%s new=%s",
        reservation_id,
        scope,
        reason,
        old_version,
        new_version,
    )
    publish_reservation_version_changed(reservation_id, scope, new_version)


def _bump_version(
    reservation_id: int,
    scope: ReservationVersionScope,
) -> tuple[int, int]:
    updated = ReservationVersion.objects.filter(
        reservation_id=reservation_id,
        scope=scope,
    ).update(version=F("version") + 1)

    if updated:
        row = ReservationVersion.objects.get(
            reservation_id=reservation_id,
            scope=scope,
        )
        return row.version - 1, row.version

    row, created = ReservationVersion.objects.get_or_create(
        reservation_id=reservation_id,
        scope=scope,
        defaults={"version": 1},
    )
    if created:
        return 0, 1

    ReservationVersion.objects.filter(pk=row.pk).update(version=F("version") + 1)
    row.refresh_from_db(fields=["version"])
    return row.version - 1, row.version
