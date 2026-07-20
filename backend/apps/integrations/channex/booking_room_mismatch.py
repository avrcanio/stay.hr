from __future__ import annotations

import logging

from apps.integrations.models import ChannexBookingRevision
from apps.reservations.channel_sync import is_pdf_authoritative
from apps.reservations.models import Reservation, ReservationUnit

logger = logging.getLogger(__name__)

CHANNEX_ROOMS_MISMATCH_NOTE = "CHANNEX_ROOMS_MISMATCH:"
CHANNEX_EMPTY_ROOMS_NOTE = "CHANNEX_EMPTY_ROOMS:"
MULTI_ROOM_SUSPECT_NOTE = "MULTI_ROOM_SUSPECT:"


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


def should_preserve_units_on_channex_ingest(
    *,
    reservation: Reservation,
    created: bool,
    channex_rooms_count: int,
    incoming_status: str,
) -> bool:
    """
    Keep stay.hr units when a later Channex revision under-reports rooms.

    Channex is the channel manager but its booking revision payload can list
    fewer rooms than Booking.com sold (or than stay.hr already corrected via
    XLS/PDF). Blind delete+recreate would drop mapped units and reopen calendar.
    """
    if is_pdf_authoritative(reservation):
        return True
    if created:
        return False
    if incoming_status in {
        Reservation.Status.CANCELED,
        Reservation.Status.NO_SHOW,
    }:
        # Booking.com cancel revisions often omit dates and rooms; keep units for ARI reopen.
        mapped = _count_mapped_units(reservation)
        return mapped > 0 and channex_rooms_count == 0
    mapped = _count_mapped_units(reservation)
    return mapped > 0 and channex_rooms_count < mapped


def detect_stay_hr_unit_gaps(reservation: Reservation) -> list[str]:
    """Detect multi-room count in stay.hr without a matching ReservationUnit row."""
    mapped = _count_mapped_units(reservation)
    units_count = reservation.units_count or 0
    issues: list[str] = []
    if units_count >= 2 and mapped < units_count:
        issues.append(
            f"units_count={units_count} ali samo {mapped} mapped unit — provjeri PDF import"
        )
    return issues


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

    issues.extend(detect_stay_hr_unit_gaps(reservation))

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
    _force_property_close_after_room_warning(
        reservation,
        reason="channex_rooms_mismatch",
    )
    return issues


def _force_property_close_after_room_warning(
    reservation: Reservation,
    *,
    reason: str,
) -> None:
    """Close all property room types so under-reported multi-room cannot resell nights."""
    try:
        from apps.integrations.channex.reservation_availability_service import (
            force_close_property_channex_availability,
        )

        force_close_property_channex_availability(reservation, reason=reason)
    except Exception:
        logger.exception(
            "channex property-wide ARI close failed after room warning",
            extra={"reservation_id": reservation.pk, "reason": reason},
        )


def _append_reservation_warning_note(
    reservation: Reservation,
    *,
    prefix: str,
    message: str,
) -> None:
    if prefix in (reservation.notes or ""):
        return
    line = f"{prefix} {message}"
    existing = (reservation.notes or "").strip()
    reservation.notes = f"{existing}\n{line}".strip() if existing else line
    reservation.save(update_fields=["notes", "updated_at"])


def flag_channex_ingest_room_warnings(
    reservation: Reservation,
    *,
    channex_rooms_count: int,
    adults_count: int,
) -> list[str]:
    """
    Warn when Channex ingest under-reports rooms (empty or single room for 4+ adults).

    Catches the Philippe/Kukla pattern before a second booking sells the same night.
    """
    if reservation.status in {
        Reservation.Status.CANCELED,
        Reservation.Status.NO_SHOW,
    }:
        return []

    issues: list[str] = []
    if channex_rooms_count == 0:
        issues.append(
            "Channex revision rooms=0 — provjeri B.com PDF i multi-room prije nego kanal ostane otvoren"
        )
        _append_reservation_warning_note(
            reservation,
            prefix=CHANNEX_EMPTY_ROOMS_NOTE,
            message=issues[-1],
        )
    elif channex_rooms_count == 1 and adults_count >= 4:
        issues.append(
            f"Channex samo 1 soba, {adults_count} odraslih — provjeri multi-room PDF import"
        )
        _append_reservation_warning_note(
            reservation,
            prefix=MULTI_ROOM_SUSPECT_NOTE,
            message=issues[-1],
        )

    if issues:
        _notify_channex_room_mismatch(reservation, issues)
        logger.warning(
            "channex ingest room warning",
            extra={
                "reservation_id": reservation.pk,
                "booking_code": reservation.booking_code,
                "channex_rooms_count": channex_rooms_count,
                "adults_count": adults_count,
                "issues": issues,
            },
        )
        reason = (
            "channex_empty_rooms"
            if channex_rooms_count == 0
            else "multi_room_suspect"
        )
        _force_property_close_after_room_warning(reservation, reason=reason)
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
        .order_by("-acknowledged_at")
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
        stay_issues = detect_stay_hr_unit_gaps(reservation)
        result["issues"] = stay_issues or (
            ["Nema Channex revision u stay.hr"]
            if reservation.import_source == "channex"
            else []
        )
        return result

    payload = getattr(revision, "payload", None) or {}
    if not isinstance(payload, dict):
        payload = {}
    attrs = payload.get("attributes") or payload
    if not isinstance(attrs, dict):
        attrs = {}
    channex_rooms = _count_channex_rooms(attrs if isinstance(attrs, dict) else {})
    result["channex_rooms"] = channex_rooms
    result["issues"] = detect_channex_room_mismatch(
        reservation,
        channex_rooms_count=channex_rooms,
    )
    if not result["issues"]:
        result["issues"] = detect_stay_hr_unit_gaps(reservation)
    return result
