from __future__ import annotations

from datetime import datetime
from typing import Literal

from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

IMPORT_SOURCE_BOOKING_XLS = "booking_xls"
IMPORT_SOURCE_SMOOBU = "smoobu"

ChannelSource = Literal["booking_xls", "smoobu"]


def find_reservation_for_channel_merge(
    *,
    tenant: Tenant,
    booking_code: str = "",
    smoobu_booking_id: str = "",
    external_id: str = "",
) -> Reservation | None:
    smoobu_id = (smoobu_booking_id or "").strip()
    if smoobu_id:
        found = Reservation.objects.filter(
            tenant=tenant,
            external_id=smoobu_id,
            import_source=IMPORT_SOURCE_SMOOBU,
        ).first()
        if found is not None:
            return found
        found = Reservation.objects.filter(
            tenant=tenant,
            smoobu_booking_id=smoobu_id,
        ).first()
        if found is not None:
            return found

    code = (booking_code or "").strip()
    if code:
        found = Reservation.objects.filter(
            tenant=tenant,
            booking_code=code,
        ).first()
        if found is not None:
            return found

    ext = (external_id or "").strip()
    if ext:
        return Reservation.objects.filter(
            tenant=tenant,
            external_id=ext,
        ).first()
    return None


def opponent_timestamp(
    existing: Reservation,
    *,
    source: ChannelSource,
) -> datetime | None:
    if source == IMPORT_SOURCE_SMOOBU:
        return existing.xls_imported_at
    return existing.smoobu_modified_at


def incoming_wins(
    existing: Reservation,
    *,
    source: ChannelSource,
    incoming_at: datetime,
) -> bool:
    opponent_at = opponent_timestamp(existing, source=source)
    if opponent_at is None:
        return True
    return incoming_at >= opponent_at
