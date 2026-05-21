from __future__ import annotations

import logging
from typing import Any

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.booking_service import process_smoobu_booking
from apps.integrations.smoobu.client import SmoobuClient
from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuApiError, SmoobuBookingIngestError

logger = logging.getLogger(__name__)

BOOKING_ACTIONS = frozenset(
    {
        "newReservation",
        "updateReservation",
        "cancelReservation",
        "deleteReservation",
    }
)


def find_smoobu_integration() -> IntegrationConfig | None:
    return (
        IntegrationConfig.objects.filter(
            provider=IntegrationConfig.Provider.SMOOBU,
            is_active=True,
        )
        .select_related("tenant", "property")
        .order_by("tenant_id")
        .first()
    )


def extract_action(body: dict[str, Any]) -> str:
    return str(body.get("action") or body.get("type") or "").strip()


def extract_booking_payload(body: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("booking", "reservation", "data"):
        value = body.get(key)
        if isinstance(value, dict) and value.get("id") is not None:
            return value
    if body.get("id") is not None:
        return body
    return None


def fetch_booking_by_id(
    config: SmoobuRuntimeConfig,
    booking_id: str | int,
) -> dict[str, Any] | None:
    with SmoobuClient(config) as client:
        page = 1
        target = str(booking_id).strip()
        while page <= 20:
            payload = client.get_reservations(page=page, page_size=100)
            bookings = payload.get("bookings") or []
            if not isinstance(bookings, list):
                break
            for item in bookings:
                if isinstance(item, dict) and str(item.get("id")) == target:
                    return item
            page_count = int(payload.get("page_count") or 1)
            if page >= page_count:
                break
            page += 1
    return None


def record_smoobu_webhook(
    *,
    integration_row: IntegrationConfig,
    action: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    if action == "updateRates":
        logger.info("smoobu webhook ignored: updateRates")
        return {"status": "ignored", "action": action}

    if action not in BOOKING_ACTIONS:
        logger.info("smoobu webhook ignored", extra={"action": action})
        return {"status": "ignored", "action": action}

    booking = extract_booking_payload(body)
    config = SmoobuRuntimeConfig.from_integration_dict(integration_row.get_config_dict())

    if booking is None:
        booking_id = body.get("id") or body.get("bookingId") or body.get("booking_id")
        if booking_id is None:
            raise SmoobuBookingIngestError("Smoobu webhook missing booking id.")
        try:
            booking = fetch_booking_by_id(config, booking_id)
        except SmoobuApiError as exc:
            raise SmoobuBookingIngestError(str(exc)) from exc
        if booking is None:
            raise SmoobuBookingIngestError(f"Smoobu booking {booking_id} not found via API.")

    if action in {"cancelReservation", "deleteReservation"}:
        booking = dict(booking)
        booking["type"] = "cancellation"

    result = process_smoobu_booking(integration_row, booking, config=config)
    return {
        "status": "ok",
        "action": action,
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "reservation_id": result.reservation.id if result.reservation else None,
    }
