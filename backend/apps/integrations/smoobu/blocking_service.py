from __future__ import annotations

from datetime import date

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.client import SmoobuClient
from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuRatesError
from apps.properties.models import Unit

SMOOBU_BLOCKED_CHANNEL_ID = 11


def block_apartment_dates(
    integration_row: IntegrationConfig,
    *,
    unit_code: str,
    check_in: date,
    check_out: date,
    notice: str = "",
    guest_label: str = "Block",
    client: SmoobuClient | None = None,
) -> dict:
    """Create a Smoobu blocked-booking (channel 11) for one apartment and date range."""
    if check_out <= check_in:
        raise SmoobuRatesError("check_out must be after check_in")

    config = SmoobuRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    unit = Unit.objects.get(tenant=integration_row.tenant, code=unit_code)
    apartment_id = config.apartment_id_for_unit_code(unit.code)
    if apartment_id is None:
        raise SmoobuRatesError(f"No Smoobu apartment mapping for unit {unit_code}")

    owns_client = client is None
    if owns_client:
        client = SmoobuClient(config)

    payload = {
        "arrivalDate": check_in.isoformat(),
        "departureDate": check_out.isoformat(),
        "channelId": SMOOBU_BLOCKED_CHANNEL_ID,
        "apartmentId": apartment_id,
        "firstName": guest_label,
        "lastName": unit_code,
        "email": "block@stay.hr.local",
        "notice": notice or f"stay.hr block {unit_code} {check_in}..{check_out}",
    }

    try:
        response = client.create_reservation(payload)
    finally:
        if owns_client and client is not None:
            client.close()

    booking_id = response.get("id")
    if not booking_id:
        raise SmoobuRatesError(f"Smoobu blocked booking failed: {response}")

    return {
        "smoobu_booking_id": booking_id,
        "unit_code": unit_code,
        "apartment_id": apartment_id,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
    }
