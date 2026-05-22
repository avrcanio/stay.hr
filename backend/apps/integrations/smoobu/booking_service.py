from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.client import SmoobuClient
from apps.integrations.smoobu.config import SmoobuApartmentLink, SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuApiError, SmoobuBookingIngestError
from apps.properties.models import Property, Unit
from apps.reservations.channel_sync import (
    IMPORT_SOURCE_SMOOBU as CHANNEL_SMOOBU,
    find_reservation_for_channel_merge,
    incoming_wins,
)
from apps.reservations.guest_slots import ensure_adult_guest_slots
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

IMPORT_SOURCE_SMOOBU = "smoobu"
DEFAULT_PROPERTY_SLUG = "uzorita"


@dataclass
class SmoobuBookingResult:
    reservation: Reservation | None = None
    created: bool = False
    updated: bool = False
    skipped: bool = False
    skip_reason: str = ""
    error: str = ""
    old_status: str | None = None


def smoobu_external_id(booking_id: str | int) -> str:
    return str(booking_id).strip()


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    return parse_date(str(value))


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        parsed = parse_datetime(str(value).replace(" ", "T"))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _booking_field(booking: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in booking:
            return booking[key]
    return None


def _map_smoobu_status(booking: dict[str, Any]) -> str:
    booking_type = str(_booking_field(booking, "type") or "").strip().lower()
    if booking_type in {"cancellation", "cancelled", "canceled", "cancel"}:
        return Reservation.Status.CANCELED

    for key in ("status", "booking-status", "booking_status"):
        raw = str(_booking_field(booking, key) or "").strip().lower()
        if raw in {"cancelled", "canceled", "cancel", "cancellation"}:
            return Reservation.Status.CANCELED

    if _booking_field(booking, "is-blocked-booking", "is_blocked_booking") is True:
        return Reservation.Status.CANCELED

    return Reservation.Status.EXPECTED


def resolve_smoobu_property(integration_row: IntegrationConfig) -> Property:
    if integration_row.property_id:
        return integration_row.property
    tenant = integration_row.tenant
    try:
        return Property.objects.get(tenant=tenant, slug=DEFAULT_PROPERTY_SLUG)
    except Property.DoesNotExist as exc:
        prop = Property.objects.filter(tenant=tenant, is_active=True).order_by("id").first()
        if prop is None:
            raise SmoobuBookingIngestError(
                f"No property found for tenant {tenant.slug} (expected slug={DEFAULT_PROPERTY_SLUG})."
            ) from exc
        return prop


def _unit_for_apartment_link(
    tenant: Tenant,
    property: Property,
    link: SmoobuApartmentLink | None,
) -> Unit | None:
    if link is None:
        return None
    if link.unit_id:
        return Unit.objects.filter(
            tenant=tenant,
            property=property,
            id=link.unit_id,
            is_active=True,
        ).first()
    return Unit.objects.filter(
        tenant=tenant,
        property=property,
        code=link.unit_code,
        is_active=True,
    ).first()


def _parse_guest_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    if not parts:
        return "Guest", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _resolve_create_external_id(
    *,
    smoobu_id: str,
    booking_code: str,
) -> str:
    return booking_code or smoobu_id


@transaction.atomic
def _upsert_reservation_from_smoobu_booking(
    *,
    tenant: Tenant,
    property: Property,
    config: SmoobuRuntimeConfig,
    booking: dict[str, Any],
) -> SmoobuBookingResult:
    raw_id = _booking_field(booking, "id")
    if raw_id is None or str(raw_id).strip() == "":
        raise SmoobuBookingIngestError("Smoobu booking missing id.")

    smoobu_id = smoobu_external_id(raw_id)
    booking_code = str(_booking_field(booking, "reference-id", "reference_id") or "").strip()
    now = timezone.now()
    smoobu_modified = (
        _parse_datetime(_booking_field(booking, "modified-at", "modified_at")) or now
    )

    existing = find_reservation_for_channel_merge(
        tenant=tenant,
        booking_code=booking_code,
        smoobu_booking_id=smoobu_id,
        external_id=booking_code,
    )

    if existing is not None and not incoming_wins(
        existing,
        source=CHANNEL_SMOOBU,
        incoming_at=smoobu_modified,
    ):
        logger.info(
            "smoobu booking skipped: stale smoobu payload",
            extra={
                "smoobu_booking_id": smoobu_id,
                "booking_code": booking_code,
                "reservation_id": existing.id,
            },
        )
        return SmoobuBookingResult(
            skipped=True,
            skip_reason="stale_smoobu",
        )

    check_in = _parse_date(_booking_field(booking, "arrival"))
    check_out = _parse_date(_booking_field(booking, "departure"))
    if not check_in or not check_out:
        raise SmoobuBookingIngestError(
            f"Smoobu booking {external_id} missing arrival/departure dates."
        )

    apartment = _booking_field(booking, "apartment")
    apartment_id: int | None = None
    apartment_name = ""
    if isinstance(apartment, dict):
        raw_apt_id = apartment.get("id")
        if raw_apt_id is not None:
            apartment_id = int(raw_apt_id)
        apartment_name = str(apartment.get("name") or "").strip()

    link = config.link_for_apartment_id(apartment_id) if apartment_id is not None else None
    if apartment_id is not None and link is None:
        raise SmoobuBookingIngestError(
            f"No Smoobu apartment mapping for apartment_id={apartment_id}."
        )

    channel = _booking_field(booking, "channel")
    source = "Smoobu"
    if isinstance(channel, dict):
        source = str(channel.get("name") or source).strip() or source

    adults = int(_booking_field(booking, "adults") or 0)
    children = int(_booking_field(booking, "children") or 0)
    nights = (check_out - check_in).days
    new_status = _map_smoobu_status(booking)
    guest_name = str(_booking_field(booking, "guest-name", "guest_name") or "").strip()
    booker_name = guest_name or "Smoobu guest"

    defaults: dict[str, Any] = {
        "property": property,
        "check_in": check_in,
        "check_out": check_out,
        "status": new_status,
        "booker_name": booker_name,
        "booker_email": str(_booking_field(booking, "email") or "").strip(),
        "booker_phone": str(_booking_field(booking, "phone") or "").strip()[:64],
        "amount": _parse_decimal(_booking_field(booking, "price")),
        "currency": "EUR",
        "source": source,
        "import_source": IMPORT_SOURCE_SMOOBU,
        "booked_at": _parse_datetime(_booking_field(booking, "created-at", "created_at")),
        "imported_at": smoobu_modified,
        "smoobu_modified_at": smoobu_modified,
        "smoobu_booking_id": smoobu_id,
        "adults_count": adults,
        "children_count": children,
        "persons_count": adults + children,
        "nights_count": nights or None,
        "units_count": 1,
        "canceled_at": smoobu_modified if new_status == Reservation.Status.CANCELED else None,
        "details_pending": False,
    }
    if booking_code:
        defaults["booking_code"] = booking_code

    old_status: str | None = None
    if existing is None:
        reservation = Reservation.objects.create(
            tenant=tenant,
            external_id=_resolve_create_external_id(
                smoobu_id=smoobu_id,
                booking_code=booking_code,
            ),
            **defaults,
        )
        created = True
    else:
        reservation = existing
        created = False
        old_status = reservation.status
        if reservation.status in (
            Reservation.Status.CHECKED_IN,
            Reservation.Status.CHECKED_OUT,
        ):
            defaults["status"] = reservation.status
            defaults.pop("canceled_at", None)
        for field, value in defaults.items():
            setattr(reservation, field, value)
        reservation.save()

    unit = _unit_for_apartment_link(tenant, property, link)
    room_name = apartment_name or (link.unit_code if link else "Unknown")
    reservation.units.all().delete()
    ReservationUnit.objects.create(
        tenant=tenant,
        reservation=reservation,
        unit=unit,
        sort_order=0,
        room_name=room_name,
        amount=defaults.get("amount"),
    )

    if reservation.status != Reservation.Status.CANCELED and guest_name:
        first_name, last_name = _parse_guest_name(guest_name)
        Guest.objects.update_or_create(
            tenant=tenant,
            reservation=reservation,
            is_primary=True,
            defaults={
                "first_name": first_name,
                "last_name": last_name or "-",
                "name": guest_name,
                "email": defaults["booker_email"],
                "phone": defaults["booker_phone"][:32],
                "is_primary": True,
            },
        )
        ensure_adult_guest_slots(
            tenant=tenant,
            reservation=reservation,
            adults_count=reservation.adults_count,
        )

    return SmoobuBookingResult(
        reservation=reservation,
        created=created,
        updated=not created,
        old_status=old_status,
    )


def process_smoobu_booking(
    integration_row: IntegrationConfig,
    booking: dict[str, Any],
    *,
    config: SmoobuRuntimeConfig | None = None,
) -> SmoobuBookingResult:
    runtime = config or SmoobuRuntimeConfig.from_integration_dict(
        integration_row.get_config_dict()
    )
    tenant = integration_row.tenant
    property = resolve_smoobu_property(integration_row)

    try:
        with transaction.atomic():
            result = _upsert_reservation_from_smoobu_booking(
                tenant=tenant,
                property=property,
                config=runtime,
                booking=booking,
            )
    except SmoobuBookingIngestError:
        raise
    except Exception as exc:
        raise SmoobuBookingIngestError(str(exc)) from exc

    if (
        result.reservation
        and result.updated
        and result.old_status
        and result.old_status != result.reservation.status
    ):
        from apps.core.tasks import notify_reservation_status_changed

        notify_reservation_status_changed.delay(
            result.reservation.pk,
            result.old_status,
            result.reservation.status,
        )

    logger.info(
        "smoobu booking processed",
        extra={
            "external_id": smoobu_external_id(booking.get("id", "")),
            "reservation_id": result.reservation.id if result.reservation else None,
            "reservation_created": result.created,
            "reservation_updated": result.updated,
            "reservation_skipped": result.skipped,
        },
    )
    return result


def _max_modified_at(bookings: list[dict[str, Any]], current: str | None) -> str | None:
    best = current
    for booking in bookings:
        modified = str(_booking_field(booking, "modified-at", "modified_at") or "").strip()
        if not modified:
            continue
        if best is None or modified > best:
            best = modified
    return best


def default_modified_from(integration_row: IntegrationConfig) -> str:
    data = integration_row.get_config_dict()
    stored = str(data.get("last_sync_modified_from") or "").strip()
    if stored:
        return stored
    return (timezone.now() - timedelta(days=30)).strftime("%Y-%m-%d")


def sync_smoobu_reservations(
    integration_row: IntegrationConfig,
    *,
    modified_from: str | None = None,
    apartment_id: int | None = None,
    dry_run: bool = False,
    client: SmoobuClient | None = None,
) -> dict[str, Any]:
    config = SmoobuRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    modified_from = (modified_from or default_modified_from(integration_row)).strip()

    stats: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "modified_from": modified_from,
    }

    owns_client = client is None
    if owns_client:
        client = SmoobuClient(config)

    processed_bookings: list[dict[str, Any]] = []
    try:
        bookings = client.iter_reservations(
            modified_from=modified_from,
            apartment_id=apartment_id,
        )
        for booking in bookings:
            if dry_run:
                stats["created"] += 1
                processed_bookings.append(booking)
                continue
            try:
                result = process_smoobu_booking(
                    integration_row,
                    booking,
                    config=config,
                )
                processed_bookings.append(booking)
                if result.skipped:
                    stats["skipped"] += 1
                elif result.created:
                    stats["created"] += 1
                elif result.updated:
                    stats["updated"] += 1
            except SmoobuBookingIngestError as exc:
                external_id = smoobu_external_id(booking.get("id", ""))
                stats["errors"].append({"external_id": external_id, "error": str(exc)})
                logger.warning(
                    "smoobu booking ingest error",
                    extra={"external_id": external_id, "error": str(exc)},
                )
    except SmoobuApiError as exc:
        raise SmoobuBookingIngestError(str(exc)) from exc
    finally:
        if owns_client and client is not None:
            client.close()

    if not dry_run and processed_bookings:
        new_cursor = _max_modified_at(
            processed_bookings,
            str(integration_row.get_config_dict().get("last_sync_modified_from") or ""),
        )
        if new_cursor:
            data = integration_row.get_config_dict()
            data["last_sync_modified_from"] = new_cursor
            integration_row.set_config_dict(data)
            integration_row.save(update_fields=["config_encrypted", "config", "updated_at"])
            stats["last_sync_modified_from"] = new_cursor

    return stats
