from __future__ import annotations

import logging
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.integrations.channex.booking_test import CHANNEX_BOOKING_TEST_PROPERTY_SLUG
from apps.integrations.channex.client import ChannexClient
from apps.integrations.channex.config import ChannexBookingTestRoomLink, ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.integrations.models import ChannexBookingRevision, IntegrationConfig
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

CHANNEX_EXTERNAL_ID_PREFIX = "channex:"


def channex_external_id(booking_id: str) -> str:
    booking_id = booking_id.strip()
    if booking_id.startswith(CHANNEX_EXTERNAL_ID_PREFIX):
        return booking_id
    return f"{CHANNEX_EXTERNAL_ID_PREFIX}{booking_id}"


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
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _customer_name(customer: dict[str, Any]) -> str:
    parts = [str(customer.get("name") or "").strip(), str(customer.get("surname") or "").strip()]
    full = " ".join(part for part in parts if part)
    return full or str(customer.get("mail") or "Channex guest")


def _map_reservation_status(channex_status: str) -> str:
    status = (channex_status or "").strip().lower()
    if status == "cancelled":
        return Reservation.Status.CANCELED
    return Reservation.Status.EXPECTED


def resolve_certification_property(
    tenant: Tenant,
    config: ChannexRuntimeConfig,
) -> Property:
    slug = config.certification_property_slug or CHANNEX_BOOKING_TEST_PROPERTY_SLUG
    try:
        return Property.objects.get(tenant=tenant, slug=slug)
    except Property.DoesNotExist as exc:
        raise ChannexBookingIngestError(
            f"Certification property '{slug}' not found for tenant {tenant.slug}."
        ) from exc


def _unit_for_room_link(
    tenant: Tenant,
    property: Property,
    room_link: ChannexBookingTestRoomLink,
) -> Unit | None:
    if room_link.unit_id:
        return Unit.objects.filter(
            tenant=tenant,
            property=property,
            id=room_link.unit_id,
            is_active=True,
        ).first()
    return Unit.objects.filter(
        tenant=tenant,
        property=property,
        code=room_link.unit_code,
        is_active=True,
    ).first()


@transaction.atomic
def _upsert_reservation_from_revision(
    *,
    tenant: Tenant,
    property: Property,
    config: ChannexRuntimeConfig,
    revision: dict[str, Any],
) -> tuple[Reservation, bool]:
    attrs = revision.get("attributes") or {}
    booking_id = str(attrs.get("booking_id") or revision.get("booking_id") or "").strip()
    if not booking_id:
        raise ChannexBookingIngestError("Booking revision missing booking_id.")

    check_in = _parse_date(attrs.get("arrival_date"))
    check_out = _parse_date(attrs.get("departure_date"))
    if not check_in or not check_out:
        raise ChannexBookingIngestError("Booking revision missing arrival/departure dates.")

    customer = attrs.get("customer") if isinstance(attrs.get("customer"), dict) else {}
    occupancy = attrs.get("occupancy") if isinstance(attrs.get("occupancy"), dict) else {}
    nights = (check_out - check_in).days
    if nights < 0:
        nights = 0

    booking_code = str(
        attrs.get("ota_reservation_code") or attrs.get("unique_id") or attrs.get("system_id") or ""
    ).strip()

    defaults: dict[str, Any] = {
        "property": property,
        "check_in": check_in,
        "check_out": check_out,
        "status": _map_reservation_status(str(attrs.get("status") or "")),
        "booking_status": str(attrs.get("status") or ""),
        "booker_name": _customer_name(customer),
        "booker_email": str(customer.get("mail") or "").strip(),
        "booker_phone": str(customer.get("phone") or "").strip(),
        "booker_country": str(customer.get("country") or "").strip()[:8],
        "booker_address": str(customer.get("address") or "").strip(),
        "amount": _parse_decimal(attrs.get("amount")),
        "currency": str(attrs.get("currency") or "GBP").strip()[:3] or "GBP",
        "source": str(attrs.get("ota_name") or "Channex").strip(),
        "import_source": "channex",
        "booked_at": _parse_datetime(attrs.get("inserted_at")),
        "adults_count": int(occupancy.get("adults") or 0) or None,
        "children_count": int(occupancy.get("children") or 0) or None,
        "nights_count": nights or None,
        "notes": str(attrs.get("notes") or "").strip(),
        "canceled_at": timezone.now()
        if _map_reservation_status(str(attrs.get("status") or "")) == Reservation.Status.CANCELED
        else None,
        "details_pending": False,
    }

    reservation, created = Reservation.objects.update_or_create(
        tenant=tenant,
        external_id=channex_external_id(booking_id),
        defaults=defaults,
    )

    if booking_code and reservation.booking_code != booking_code:
        reservation.booking_code = booking_code
        reservation.save(update_fields=["booking_code", "updated_at"])

    rooms = attrs.get("rooms") or []
    if not isinstance(rooms, list):
        rooms = []

    reservation.units.all().delete()
    units_count = 0
    for index, room in enumerate(rooms):
        if not isinstance(room, dict):
            continue
        room_type_id = str(room.get("room_type_id") or "").strip()
        room_link = config.booking_test_room_for_channex_room_type_id(room_type_id)
        unit = _unit_for_room_link(tenant, property, room_link) if room_link else None
        room_name = (
            (room_link.channex_title if room_link else "")
            or str(room.get("room_type_name") or "")
            or room_type_id
            or f"Room {index + 1}"
        )
        ReservationUnit.objects.create(
            tenant=tenant,
            reservation=reservation,
            unit=unit,
            sort_order=index,
            room_name=room_name,
            amount=_parse_decimal(room.get("amount")),
        )
        units_count += 1

    if units_count:
        reservation.units_count = units_count
        reservation.save(update_fields=["units_count", "updated_at"])

    if customer and reservation.status != Reservation.Status.CANCELED:
        first = str(customer.get("name") or "").strip() or "Guest"
        last = str(customer.get("surname") or "").strip()
        guest_defaults = {
            "first_name": first,
            "last_name": last,
            "name": _customer_name(customer),
            "email": str(customer.get("mail") or "").strip(),
            "phone": str(customer.get("phone") or "").strip()[:32],
            "address": str(customer.get("address") or "").strip(),
            "is_primary": True,
        }
        Guest.objects.update_or_create(
            tenant=tenant,
            reservation=reservation,
            is_primary=True,
            defaults=guest_defaults,
        )

    return reservation, created


def process_channex_booking_revision(
    integration_row: IntegrationConfig,
    revision_id: str,
    *,
    client: ChannexClient | None = None,
) -> Reservation:
    revision_id = revision_id.strip()
    if not revision_id:
        raise ChannexBookingIngestError("revision_id is required.")

    if ChannexBookingRevision.objects.filter(revision_id=revision_id).exists():
        existing = ChannexBookingRevision.objects.select_related("reservation").get(
            revision_id=revision_id
        )
        logger.info(
            "channex booking revision already processed",
            extra={"revision_id": revision_id, "reservation_id": existing.reservation_id},
        )
        return existing.reservation

    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    tenant = integration_row.tenant
    property = resolve_certification_property(tenant, config)

    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)

    try:
        revision = client.get_booking_revision(revision_id)
        attrs = revision.get("attributes") or {}
        booking_id = str(attrs.get("booking_id") or "").strip()
        channex_status = str(attrs.get("status") or "")

        with transaction.atomic():
            reservation, created = _upsert_reservation_from_revision(
                tenant=tenant,
                property=property,
                config=config,
                revision=revision,
            )

        client.acknowledge_booking_revision(revision_id)

        ChannexBookingRevision.objects.create(
            tenant=tenant,
            revision_id=revision_id,
            booking_id=booking_id,
            reservation=reservation,
            channex_status=channex_status,
        )

        logger.info(
            "channex booking ingested and acknowledged",
            extra={
                "revision_id": revision_id,
                "booking_id": booking_id,
                "reservation_id": reservation.id,
                "reservation_created": created,
                "reservation_status": reservation.status,
            },
        )
        return reservation
    finally:
        if owns_client and client is not None:
            client.close()


def process_channex_booking_webhook(
    integration_row: IntegrationConfig,
    *,
    revision_id: str,
    booking_id: str,
    event: str,
) -> Reservation | None:
    if not revision_id:
        logger.warning(
            "channex booking webhook missing revision_id",
            extra={"event": event, "booking_id": booking_id},
        )
        return None
    return process_channex_booking_revision(integration_row, revision_id)
