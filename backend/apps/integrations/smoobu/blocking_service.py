from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.integrations.models import IntegrationConfig, UnitAvailabilityBlock
from apps.integrations.smoobu.client import SmoobuClient
from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuApiError, SmoobuRatesError
from apps.properties.models import Unit

SMOOBU_BLOCKED_CHANNEL_ID = 11
HOSPIRA_BLOCK_EMAIL = "block@stay.hr.local"


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

    smoobu_id = str(booking_id)
    with transaction.atomic():
        block_row = UnitAvailabilityBlock.objects.create(
            tenant=integration_row.tenant,
            unit=unit,
            check_in=check_in,
            check_out=check_out,
            smoobu_booking_id=smoobu_id,
            created_via=UnitAvailabilityBlock.CreatedVia.HOSPIRA,
        )

    return {
        "id": block_row.id,
        "smoobu_booking_id": smoobu_id,
        "unit_code": unit_code,
        "unit_id": unit.id,
        "apartment_id": apartment_id,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
    }


def unblock_apartment_dates(
    block_row: UnitAvailabilityBlock,
    *,
    client: SmoobuClient | None = None,
) -> None:
    """Cancel Smoobu blocked booking and remove local block row."""
    if block_row.created_via != UnitAvailabilityBlock.CreatedVia.HOSPIRA:
        raise SmoobuRatesError("Only Hospira-created blocks can be unblocked via API.")

    integration_row = IntegrationConfig.objects.filter(
        tenant=block_row.tenant,
        provider=IntegrationConfig.Provider.SMOOBU,
        is_active=True,
    ).order_by("-property_id").first()
    if integration_row is None:
        raise SmoobuRatesError("No active Smoobu integration.")

    config = SmoobuRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    owns_client = client is None
    if owns_client:
        client = SmoobuClient(config)

    try:
        client.cancel_reservation(block_row.smoobu_booking_id)
    except SmoobuApiError as exc:
        raise SmoobuRatesError(str(exc)) from exc
    finally:
        if owns_client and client is not None:
            client.close()

    block_row.delete()
