from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.integrations.channex.booking_service import (
    channex_external_id,
    parse_channex_booking_id,
)
from apps.integrations.channex.client import ChannexClient
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.models import ChannexMessage, IntegrationConfig
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


def find_reservation_for_channex_booking(tenant: Tenant, booking_id: str) -> Reservation | None:
    booking_id = (booking_id or "").strip()
    if not booking_id:
        return None
    return (
        Reservation.objects.filter(
            tenant=tenant,
            external_id=channex_external_id(booking_id),
        )
        .first()
    )


def channex_message_id_from_payload(payload: dict[str, Any]) -> str:
    for key in ("id", "ota_message_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    raise ChannexBookingIngestError("Channex message payload missing id.")


def _flatten_message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    attrs = payload.get("attributes")
    if isinstance(attrs, dict):
        merged = dict(attrs)
        if payload.get("id") and not merged.get("id"):
            merged["id"] = payload["id"]
        thread = (payload.get("relationships") or {}).get("message_thread") or {}
        thread_data = thread.get("data") if isinstance(thread, dict) else None
        if isinstance(thread_data, dict) and thread_data.get("id"):
            merged.setdefault("message_thread_id", str(thread_data["id"]))
        return merged
    return payload


def _message_created_at(payload: dict[str, Any]) -> datetime | None:
    for key in ("inserted_at", "created_at"):
        raw = payload.get(key)
        if not raw:
            continue
        parsed = parse_datetime(str(raw).replace("Z", "+00:00"))
        if parsed is None:
            continue
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt_timezone.utc)
        return parsed
    return None


def _message_body(payload: dict[str, Any]) -> str:
    return str(payload.get("message") or payload.get("body") or "").strip()


def _message_sender(payload: dict[str, Any]) -> str:
    sender = str(payload.get("sender") or "").strip().lower()
    if sender == ChannexMessage.Sender.GUEST:
        return ChannexMessage.Sender.GUEST
    return ChannexMessage.Sender.PROPERTY


def _direction_for_sender(sender: str) -> str:
    if sender == ChannexMessage.Sender.GUEST:
        return ChannexMessage.Direction.INBOUND
    return ChannexMessage.Direction.OUTBOUND


def _extract_message_rows(api_response: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in api_response.get("data") or []:
        if isinstance(item, dict):
            rows.append(_flatten_message_payload(item))
    data = api_response.get("data")
    if isinstance(data, dict):
        rows.append(_flatten_message_payload(data))
    return rows


def upsert_channex_message_from_payload(
    *,
    tenant: Tenant,
    integration: IntegrationConfig,
    payload: dict[str, Any],
    reservation: Reservation | None = None,
) -> tuple[ChannexMessage, bool]:
    flat = _flatten_message_payload(payload)
    message_id = channex_message_id_from_payload(flat)
    existing = ChannexMessage.objects.filter(channex_message_id=message_id).first()
    if existing is not None:
        return existing, False

    booking_id = str(flat.get("booking_id") or "").strip()
    if reservation is None and booking_id:
        reservation = find_reservation_for_channex_booking(tenant, booking_id)

    sender = _message_sender(flat)
    create_kwargs: dict[str, Any] = {
        "tenant": tenant,
        "integration": integration,
        "reservation": reservation,
        "channex_booking_id": booking_id,
        "message_thread_id": str(flat.get("message_thread_id") or "").strip(),
        "channex_message_id": message_id,
        "direction": _direction_for_sender(sender),
        "sender": sender,
        "body": _message_body(flat),
        "have_attachment": bool(flat.get("have_attachment")),
        "raw_payload": flat,
    }
    inserted_at = _message_created_at(flat)
    row = ChannexMessage.objects.create(**create_kwargs)
    if inserted_at is not None:
        ChannexMessage.objects.filter(pk=row.pk).update(created_at=inserted_at)
        row.created_at = inserted_at
    if reservation is None and booking_id:
        logger.warning(
            "channex message stored without reservation link",
            extra={
                "tenant_slug": tenant.slug,
                "booking_id": booking_id,
                "message_id": message_id,
            },
        )
    return row, True


def process_channex_message_webhook(
    integration_row: IntegrationConfig,
    *,
    property_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ChannexBookingIngestError("Channex message webhook missing payload.")

    tenant = integration_row.tenant
    booking_id = str(payload.get("booking_id") or "").strip()
    reservation = find_reservation_for_channex_booking(tenant, booking_id) if booking_id else None
    row, created = upsert_channex_message_from_payload(
        tenant=tenant,
        integration=integration_row,
        payload=payload,
        reservation=reservation,
    )
    logger.info(
        "channex message webhook processed",
        extra={
            "tenant_slug": tenant.slug,
            "property_id": property_id,
            "booking_id": booking_id,
            "message_id": row.channex_message_id,
            "message_created": created,
            "reservation_id": row.reservation_id,
        },
    )
    return {
        "message_id": row.channex_message_id,
        "created": created,
        "reservation_id": row.reservation_id,
    }


def sync_booking_messages_from_channex(
    integration_row: IntegrationConfig,
    reservation: Reservation,
    *,
    client: ChannexClient | None = None,
) -> list[ChannexMessage]:
    booking_id = parse_channex_booking_id(reservation.external_id)
    if not booking_id:
        raise ChannexBookingIngestError("Reservation is not linked to a Channex booking.")

    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)

    stored: list[ChannexMessage] = []
    try:
        response = client.list_booking_messages(booking_id)
        for row_payload in _extract_message_rows(response):
            if not row_payload.get("booking_id"):
                row_payload = {**row_payload, "booking_id": booking_id}
            message, _created = upsert_channex_message_from_payload(
                tenant=reservation.tenant,
                integration=integration_row,
                payload=row_payload,
                reservation=reservation,
            )
            stored.append(message)
    finally:
        if owns_client and client is not None:
            client.close()
    return stored


def list_messages_for_reservation(
    integration_row: IntegrationConfig,
    reservation: Reservation,
    *,
    sync_if_empty: bool = True,
    force_sync: bool = False,
    client: ChannexClient | None = None,
) -> list[ChannexMessage]:
    qs = ChannexMessage.objects.filter(
        tenant=reservation.tenant,
        reservation=reservation,
    )
    booking_id = parse_channex_booking_id(reservation.external_id)
    if booking_id and (force_sync or (sync_if_empty and not qs.exists())):
        sync_booking_messages_from_channex(
            integration_row,
            reservation,
            client=client,
        )
    return list(qs.order_by("-created_at"))


def send_message_for_reservation(
    integration_row: IntegrationConfig,
    reservation: Reservation,
    message: str,
    *,
    client: ChannexClient | None = None,
) -> ChannexMessage:
    text = (message or "").strip()
    if not text:
        raise ChannexBookingIngestError("Message body is required.")

    booking_id = parse_channex_booking_id(reservation.external_id)
    if not booking_id:
        raise ChannexBookingIngestError("Reservation is not linked to a Channex booking.")

    if reservation.import_source != "channex":
        raise ChannexBookingIngestError("Reservation was not imported from Channex.")

    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)

    try:
        response = client.send_booking_message(booking_id, text)
        rows = _extract_message_rows(response)
        payload: dict[str, Any]
        if rows:
            payload = rows[0]
        else:
            payload = {
                "id": f"local-outbound:{reservation.pk}:{ChannexMessage.objects.count() + 1}",
                "booking_id": booking_id,
                "sender": ChannexMessage.Sender.PROPERTY,
                "message": text,
            }
        if not payload.get("booking_id"):
            payload = {**payload, "booking_id": booking_id}
        if payload.get("sender") != ChannexMessage.Sender.PROPERTY:
            payload = {**payload, "sender": ChannexMessage.Sender.PROPERTY}
        row, _created = upsert_channex_message_from_payload(
            tenant=reservation.tenant,
            integration=integration_row,
            payload=payload,
            reservation=reservation,
        )
        return row
    except ChannexApiError:
        raise
    finally:
        if owns_client and client is not None:
            client.close()


def serialize_channex_message(row: ChannexMessage) -> dict[str, Any]:
    return {
        "id": row.pk,
        "channex_message_id": row.channex_message_id,
        "direction": row.direction,
        "sender": row.sender,
        "body": row.body,
        "have_attachment": row.have_attachment,
        "message_thread_id": row.message_thread_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
