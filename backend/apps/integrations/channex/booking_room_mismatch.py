from __future__ import annotations

import logging

from apps.integrations.models import ChannexBookingRevision
from apps.reservations.channel_sync import is_pdf_authoritative
from apps.reservations.models import Reservation, ReservationUnit

logger = logging.getLogger(__name__)

CHANNEX_ROOMS_MISMATCH_NOTE = "CHANNEX_ROOMS_MISMATCH:"


def _count_channex_rooms(attrs: dict) -> int:
    rooms = attrs.get("rooms") or []
    if not isinstance(rooms, list):
        return 0
    return sum(1 for room in rooms if isinstance(room, dict))


def _count_mapped_units(reservation: Reservation) -> int:
    return ReservationUnit.objects.filter(
        reservation=reservation,
        unit_id__isnull=False,
    ).count()


def detect_channex_room_mismatch(
    reservation: Reservation,
    *,
    channex_rooms_count: int,
) -> list[str]:
    issues: list[str] = []
    mapped = _count_mapped_units(reservation)
    units_count = reservation.units_count or 0

    if channex_rooms_count != units_count and units_count > 0:
        issues.append(
            f"Channex rooms={channex_rooms_count}, stay.hr units_count={units_count}"
        )

    if channex_rooms_count > 1 and mapped <= 1:
        issues.append(
            f"Channex multi-room ({channex_rooms_count}) ali samo {mapped} mapped unit u stay.hr"
        )

    if units_count >= 2 and mapped <= 1:
        issues.append(
            f"units_count={units_count} ali samo {mapped} mapped unit — provjeri PDF import"
        )

    if is_pdf_authoritative(reservation) and channex_rooms_count < mapped:
        issues.append(
            f"PDF lock: stay.hr ima {mapped} soba, Channex revision samo {channex_rooms_count}"
        )

    return issues


def _notify_channex_room_mismatch(reservation: Reservation, issues: list[str]) -> None:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data

    body = "; ".join(issues)
    title = "Channex rooms mismatch"
    data = reception_push_data(
        event_type="reservation.channex_rooms_mismatch",
        reservation_id=reservation.pk,
        summary=body,
        booking_code=reservation.booking_code or str(reservation.pk),
        check_in=reservation.check_in.isoformat(),
        check_out=reservation.check_out.isoformat(),
        status=reservation.status,
        tenant_id=str(reservation.tenant_id),
    )
    send_tenant_reception_push(
        tenant_id=reservation.tenant_id,
        title=title,
        body=f"{reservation.booker_name} · {body}",
        data=data,
    )


def flag_channex_room_mismatch(
    reservation: Reservation,
    *,
    channex_rooms_count: int,
    revision_attrs: dict | None = None,
) -> list[str]:
    issues = detect_channex_room_mismatch(
        reservation,
        channex_rooms_count=channex_rooms_count,
    )
    if not issues:
        return []

    note_line = f"{CHANNEX_ROOMS_MISMATCH_NOTE} " + "; ".join(issues)
    existing = (reservation.notes or "").strip()
    if CHANNEX_ROOMS_MISMATCH_NOTE not in existing:
        reservation.notes = f"{existing}\n{note_line}".strip() if existing else note_line
        reservation.save(update_fields=["notes", "updated_at"])

    logger.warning(
        "channex rooms mismatch",
        extra={
            "reservation_id": reservation.pk,
            "booking_code": reservation.booking_code,
            "issues": issues,
            "channex_rooms_count": channex_rooms_count,
        },
    )
    _notify_channex_room_mismatch(reservation, issues)
    return issues


def check_channex_revision_room_mismatch(
    reservation: Reservation,
    revision_attrs: dict,
) -> list[str]:
    return flag_channex_room_mismatch(
        reservation,
        channex_rooms_count=_count_channex_rooms(revision_attrs),
        revision_attrs=revision_attrs,
    )


def reconcile_reservation_units(reservation: Reservation) -> dict:
    """Compare stay.hr units to latest stored Channex revision."""
    revision = (
        ChannexBookingRevision.objects.filter(reservation=reservation)
        .order_by("-created_at")
        .first()
    )
    mapped = _count_mapped_units(reservation)
    result = {
        "reservation_id": reservation.pk,
        "booking_code": reservation.booking_code,
        "units_count": reservation.units_count,
        "mapped_units": mapped,
        "import_source": reservation.import_source,
        "pdf_locked": is_pdf_authoritative(reservation),
    }
    if revision is None:
        result["channex_rooms"] = None
        result["issues"] = (
            ["Nema Channex revision u stay.hr"]
            if reservation.import_source == "channex"
            else []
        )
        return result

    payload = revision.payload or {}
    attrs = payload.get("attributes") or payload if isinstance(payload, dict) else {}
    channex_rooms = _count_channex_rooms(attrs if isinstance(attrs, dict) else {})
    result["channex_rooms"] = channex_rooms
    result["issues"] = detect_channex_room_mismatch(
        reservation,
        channex_rooms_count=channex_rooms,
    )
    return result
