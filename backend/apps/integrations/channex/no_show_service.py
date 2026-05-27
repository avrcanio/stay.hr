from __future__ import annotations

from apps.integrations.channex.booking_service import parse_channex_booking_id
from apps.integrations.channex.client import ChannexClient
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.models import IntegrationConfig
from apps.reservations.channel_sync import IMPORT_SOURCE_CHANNEX
from apps.reservations.models import Reservation


def is_channex_no_show_eligible(reservation: Reservation) -> bool:
    if reservation.import_source != IMPORT_SOURCE_CHANNEX:
        return False
    return parse_channex_booking_id(reservation.external_id) is not None


def report_no_show_for_reservation(
    integration: IntegrationConfig,
    reservation: Reservation,
    *,
    waived_fees: bool,
) -> None:
    booking_id = parse_channex_booking_id(reservation.external_id)
    if not booking_id:
        raise ChannexBookingIngestError(
            "Rezervacija nema Channex booking ID za prijavu no-showa."
        )

    config = ChannexRuntimeConfig.from_integration_dict(integration.get_config_dict())
    try:
        with ChannexClient(config) as client:
            client.report_no_show(booking_id, waived_fees=waived_fees)
    except ChannexApiError as exc:
        raise ChannexBookingIngestError(str(exc)) from exc
