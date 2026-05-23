"""Lagani fingerprinti podataka za recepcijski sync (hash provjera prije punog fetcha)."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from django.db.models import Count, Max

from apps.properties.models import Unit
from apps.reservations.models import (
    Guest,
    MonthlyStatisticsOverride,
    Reservation,
    ReservationUnit,
)

_DIGEST_LENGTH = 16


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


def _aggregate_fingerprint(qs) -> str:
    row = qs.aggregate(count=Count("id"), max_updated=Max("updated_at"))
    count = row["count"] or 0
    max_updated = row["max_updated"]
    max_part = max_updated.isoformat() if max_updated is not None else ""
    return f"{count}:{max_part}"


def reservations_version(tenant) -> str:
    qs = Reservation.objects.for_tenant(tenant)
    return _digest(f"reservations:{_aggregate_fingerprint(qs)}")


def rooms_version(tenant) -> str:
    qs = Unit.objects.for_tenant(tenant).filter(is_active=True)
    return _digest(f"rooms:{_aggregate_fingerprint(qs)}")


def statistics_version(tenant, year: int) -> str:
    comparison_year = year - 1
    prior_year = year - 2
    date_from = date(prior_year, 1, 1)
    date_to = date(year, 12, 31)

    reservation_qs = Reservation.objects.for_tenant(tenant).filter(
        check_in__gte=date_from,
        check_in__lte=date_to,
    )
    override_qs = MonthlyStatisticsOverride.objects.for_tenant(tenant).filter(
        year__in=[year, comparison_year, prior_year],
    )
    payload = (
        f"stats:{year}:"
        f"r:{_aggregate_fingerprint(reservation_qs)}|"
        f"o:{_aggregate_fingerprint(override_qs)}"
    )
    return _digest(payload)


def reservation_detail_version(tenant, reservation_id: int) -> str | None:
    reservation = (
        Reservation.objects.for_tenant(tenant).filter(pk=reservation_id).only("updated_at").first()
    )
    if reservation is None:
        return None

    guest_agg = Guest.objects.for_tenant(tenant).filter(reservation_id=reservation_id).aggregate(
        count=Count("id"),
        max_updated=Max("updated_at"),
    )
    unit_agg = (
        ReservationUnit.objects.for_tenant(tenant)
        .filter(reservation_id=reservation_id)
        .aggregate(
            count=Count("id"),
            max_updated=Max("updated_at"),
        )
    )

    guest_max = guest_agg["max_updated"]
    unit_max = unit_agg["max_updated"]
    payload = (
        f"reservation_detail:{reservation_id}:"
        f"r:{reservation.updated_at.isoformat()}:"
        f"g:{guest_agg['count'] or 0}:{guest_max.isoformat() if guest_max is not None else ''}:"
        f"u:{unit_agg['count'] or 0}:{unit_max.isoformat() if unit_max is not None else ''}"
    )
    return _digest(payload)


def build_sync_versions_payload(
    tenant,
    year: int,
    reservation_id: int | None = None,
) -> dict | None:
    year_key = str(year)
    payload = {
        "reservations": reservations_version(tenant),
        "rooms": rooms_version(tenant),
        "statistics": {year_key: statistics_version(tenant, year)},
    }
    if reservation_id is not None:
        detail = reservation_detail_version(tenant, reservation_id)
        if detail is None:
            return None
        payload["reservation_detail"] = detail
    return payload


def sync_versions_etag(payload: dict) -> str:
    """Stabilan weak ETag za cijeli sync-versions payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f'W/"{digest}"'
