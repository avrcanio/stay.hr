"""Django cache snapshot for booking reconcile compare → apply."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.booking_xls_import import BookingXlsRow
from apps.reservations.models import Reservation
from apps.reservations.reports.booking_reconcile_types import (
    BookingReconcileParams,
    BookingReconcileRow,
)
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

CACHE_PREFIX = "booking_reconcile:v1:"
CACHE_TTL_SECONDS = 3600
SNAPSHOT_SCHEMA_VERSION = 1
# Django default locmem cache has no hard item limit; log when snapshot is unusually large.
SNAPSHOT_ROW_COUNT_WARN = 3000


def content_sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _date_to_str(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def booking_xls_row_to_dict(row: BookingXlsRow) -> dict[str, Any]:
    return {
        "external_id": row.external_id,
        "booker_name": row.booker_name,
        "guest_names": list(row.guest_names),
        "check_in_date": row.check_in_date.isoformat(),
        "check_out_date": row.check_out_date.isoformat(),
        "booked_at": row.booked_at.isoformat() if row.booked_at else None,
        "booking_status": row.booking_status,
        "units_count": row.units_count,
        "persons_count": row.persons_count,
        "adults_count": row.adults_count,
        "children_count": row.children_count,
        "children_ages": row.children_ages,
        "total_amount": _decimal_to_str(row.total_amount),
        "currency": row.currency,
        "commission_percent": _decimal_to_str(row.commission_percent),
        "commission_amount": _decimal_to_str(row.commission_amount),
        "payment_status": row.payment_status,
        "payment_provider": row.payment_provider,
        "notes": row.notes,
        "booker_country": row.booker_country,
        "travel_purpose": row.travel_purpose,
        "booking_device": row.booking_device,
        "room_name": row.room_name,
        "nights_count": row.nights_count,
        "canceled_at": row.canceled_at.isoformat() if row.canceled_at else None,
        "booker_address": row.booker_address,
        "booker_phone": row.booker_phone,
        "booker_email": row.booker_email,
        "unit_amounts": [_decimal_to_str(v) for v in row.unit_amounts],
    }


def booking_xls_row_from_dict(data: dict[str, Any]) -> BookingXlsRow:
    unit_amounts_raw = data.get("unit_amounts") or []
    unit_amounts = tuple(
        Decimal(v) for v in unit_amounts_raw if v is not None and str(v).strip()
    )
    booked_at = data.get("booked_at")
    canceled_at = data.get("canceled_at")
    return BookingXlsRow(
        external_id=data["external_id"],
        booker_name=data.get("booker_name") or "",
        guest_names=list(data.get("guest_names") or []),
        check_in_date=date.fromisoformat(data["check_in_date"]),
        check_out_date=date.fromisoformat(data["check_out_date"]),
        booked_at=datetime.fromisoformat(booked_at) if booked_at else None,
        booking_status=data.get("booking_status") or "",
        units_count=data.get("units_count"),
        persons_count=data.get("persons_count"),
        adults_count=data.get("adults_count"),
        children_count=data.get("children_count"),
        children_ages=data.get("children_ages") or "",
        total_amount=Decimal(data["total_amount"]) if data.get("total_amount") else None,
        currency=data.get("currency") or "EUR",
        commission_percent=(
            Decimal(data["commission_percent"]) if data.get("commission_percent") else None
        ),
        commission_amount=(
            Decimal(data["commission_amount"]) if data.get("commission_amount") else None
        ),
        payment_status=data.get("payment_status") or "",
        payment_provider=data.get("payment_provider") or "",
        notes=data.get("notes") or "",
        booker_country=data.get("booker_country") or "",
        travel_purpose=data.get("travel_purpose") or "",
        booking_device=data.get("booking_device") or "",
        room_name=data.get("room_name") or "",
        nights_count=data.get("nights_count"),
        canceled_at=datetime.fromisoformat(canceled_at) if canceled_at else None,
        booker_address=data.get("booker_address") or "",
        booker_phone=data.get("booker_phone") or "",
        booker_email=data.get("booker_email") or "",
        unit_amounts=unit_amounts,
    )


def _params_to_dict(params: BookingReconcileParams) -> dict[str, Any]:
    return {
        "tenant_id": params.tenant.id,
        "property_id": params.property.id,
        "property_slug": params.property.slug,
        "date_axis": params.date_axis,
        "date_from": _date_to_str(params.date_from),
        "date_to_inclusive": _date_to_str(params.date_to_inclusive),
        "filename": params.filename,
    }


def _reconcile_row_to_dict(row: BookingReconcileRow) -> dict[str, Any]:
    return asdict(row)


def reservation_fingerprint(reservation: Reservation) -> str:
    """Stable hash of reconcile-relevant reservation fields at compare time."""
    parts = (
        reservation.updated_at.isoformat() if reservation.updated_at else "",
        str(reservation.amount),
        str(reservation.commission_amount),
        str(reservation.check_in),
        str(reservation.check_out),
        str(reservation.status),
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def params_from_snapshot(snapshot: dict[str, Any]) -> BookingReconcileParams:
    raw = snapshot.get("params") or {}
    meta = snapshot.get("meta") or {}
    tenant = Tenant.objects.get(id=raw["tenant_id"])
    prop = Property.objects.get(id=raw["property_id"])
    date_from_raw = raw.get("date_from")
    date_to_raw = raw.get("date_to_inclusive")
    return BookingReconcileParams(
        tenant=tenant,
        property=prop,
        date_axis=raw.get("date_axis"),
        date_from=date.fromisoformat(date_from_raw) if date_from_raw else None,
        date_to_inclusive=date.fromisoformat(date_to_raw) if date_to_raw else None,
        filename=raw.get("filename") or meta.get("filename") or "",
    )


def validate_snapshot_scope(
    snapshot: dict[str, Any],
    *,
    tenant_id: int,
    property_id: int,
) -> str | None:
    """Return error code when snapshot tenant/property does not match apply context."""
    meta = snapshot.get("meta") or {}
    params = snapshot.get("params") or {}
    snap_tenant = meta.get("tenant_id", params.get("tenant_id"))
    snap_property = meta.get("property_id", params.get("property_id"))
    if snap_tenant != tenant_id or snap_property != property_id:
        return "snapshot_scope_mismatch"
    return None


def save_booking_reconcile_snapshot(
    *,
    params: BookingReconcileParams,
    xls_rows: list[BookingXlsRow],
    result_rows: tuple[BookingReconcileRow, ...],
    content_sha256: str,
    reservation_fingerprints: dict[str, str] | None = None,
) -> str:
    snapshot_id = str(uuid.uuid4())
    created_at = timezone.now()
    if len(xls_rows) >= SNAPSHOT_ROW_COUNT_WARN:
        logger.warning(
            "booking_reconcile snapshot row_count=%s exceeds warn threshold=%s tenant_id=%s property_id=%s",
            len(xls_rows),
            SNAPSHOT_ROW_COUNT_WARN,
            params.tenant.id,
            params.property.id,
        )
    payload = {
        "meta": {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "created_at": created_at.isoformat(),
            "content_sha256": content_sha256,
            "tenant_id": params.tenant.id,
            "property_id": params.property.id,
            "filename": params.filename,
            "row_count": len(xls_rows),
        },
        "params": _params_to_dict(params),
        "xls_rows": [booking_xls_row_to_dict(row) for row in xls_rows],
        "result_rows": [_reconcile_row_to_dict(row) for row in result_rows],
        "reservation_fingerprints": reservation_fingerprints or {},
    }
    cache.set(f"{CACHE_PREFIX}{snapshot_id}", payload, CACHE_TTL_SECONDS)
    return snapshot_id


def load_booking_reconcile_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    payload = cache.get(f"{CACHE_PREFIX}{snapshot_id}")
    return payload if isinstance(payload, dict) else None


def xls_rows_by_external_id(snapshot: dict[str, Any]) -> dict[str, BookingXlsRow]:
    rows = snapshot.get("xls_rows") or []
    mapping: dict[str, BookingXlsRow] = {}
    for raw in rows:
        row = booking_xls_row_from_dict(raw)
        mapping[row.external_id] = row
    return mapping
