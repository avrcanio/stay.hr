"""Guest portal access token CRUD, window, and gate helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from django.db import transaction
from django.utils import timezone

from apps.reservations.guest_checkin_session import (
    guest_checkin_window,
    resolve_guest_checkin_base_url,
)
from apps.reservations.models import (
    GuestPortalAccess,
    GuestPortalAccessCreatedFrom,
    GuestPortalAccessStatus,
    Reservation,
)

PortalGateStatus = Literal[
    "active",
    "not_open_yet",
    "expired",
    "revoked",
]


@dataclass(frozen=True)
class PortalAccessResult:
    allowed: bool
    http_status: int
    gate_status: PortalGateStatus
    opens_at: datetime | None = None


def get_access_by_token(token) -> GuestPortalAccess | None:
    return (
        GuestPortalAccess.objects.select_related(
            "reservation",
            "reservation__property",
            "reservation__tenant",
        )
        .filter(token=token)
        .first()
    )


def get_active_portal_access(reservation: Reservation) -> GuestPortalAccess | None:
    return (
        GuestPortalAccess.objects.filter(
            reservation=reservation,
            status=GuestPortalAccessStatus.ACTIVE,
        )
        .order_by("-created_at")
        .first()
    )


def evaluate_portal_access(
    access: GuestPortalAccess,
    *,
    now: datetime | None = None,
) -> PortalAccessResult:
    now = now or timezone.now()

    if access.status == GuestPortalAccessStatus.REVOKED:
        return PortalAccessResult(False, 410, "revoked")

    if now > access.expires_at:
        return PortalAccessResult(False, 410, "expired")

    if now < access.opens_at:
        return PortalAccessResult(
            False,
            403,
            "not_open_yet",
            opens_at=access.opens_at,
        )

    return PortalAccessResult(True, 200, "active")


@transaction.atomic
def ensure_active_portal_access(
    reservation: Reservation,
    *,
    created_from: str = GuestPortalAccessCreatedFrom.SYSTEM,
) -> GuestPortalAccess:
    """Return the single active portal access for a reservation, creating if needed."""
    existing = get_active_portal_access(reservation)
    if existing is not None:
        return existing

    window = guest_checkin_window(reservation)
    return GuestPortalAccess.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        status=GuestPortalAccessStatus.ACTIVE,
        opens_at=window.opens_at,
        expires_at=window.expires_at,
        created_from=created_from,
    )


@transaction.atomic
def revoke_portal_access(access: GuestPortalAccess) -> GuestPortalAccess:
    if access.status == GuestPortalAccessStatus.REVOKED:
        return access
    access.status = GuestPortalAccessStatus.REVOKED
    access.save(update_fields=["status", "updated_at"])
    return access


@transaction.atomic
def regenerate_portal_access(
    reservation: Reservation,
    *,
    created_from: str = GuestPortalAccessCreatedFrom.RECEPTION_MANUAL,
) -> tuple[GuestPortalAccess | None, GuestPortalAccess]:
    """Revoke current active access (if any) and create a new active one."""
    old = get_active_portal_access(reservation)
    if old is not None:
        revoke_portal_access(old)
    new = ensure_active_portal_access(
        reservation,
        created_from=created_from,
    )
    return old, new


def build_guest_portal_url(access: GuestPortalAccess, reservation: Reservation) -> str:
    base = resolve_guest_checkin_base_url(reservation)
    return f"{base}/g/{access.token}"
