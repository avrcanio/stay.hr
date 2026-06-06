"""Property-wide guest message thread inbox aggregation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.communications.guest_message_timeline import last_timeline_entry
from apps.communications.models import GuestMessageThreadState, GuestOutboundMessage
from apps.core.timezone import tenant_local_now
from apps.integrations.channex.booking_service import parse_channex_booking_id
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.message_service import list_messages_for_reservation
from apps.integrations.models import ChannexMessage, IntegrationConfig, WhatsAppMessage
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

DEFAULT_PAGE_SIZE = 25


def _reservation_ids_with_messages(tenant: Tenant) -> set[int]:
    ids: set[int] = set()
    ids.update(
        GuestOutboundMessage.objects.filter(tenant=tenant).values_list("reservation_id", flat=True)
    )
    ids.update(
        WhatsAppMessage.objects.filter(tenant=tenant, reservation_id__isnull=False).values_list(
            "reservation_id", flat=True
        )
    )
    ids.update(
        ChannexMessage.objects.filter(tenant=tenant, reservation_id__isnull=False).values_list(
            "reservation_id", flat=True
        )
    )
    return {i for i in ids if i}


def _room_name_for_reservation(reservation: Reservation) -> str:
    units = list(reservation.units.all())
    if not units:
        return ""
    first = units[0]
    return (first.room_name or "").strip() or (first.unit.name if first.unit_id else "")


def _sync_channex_for_reservations(
    integration: IntegrationConfig,
    reservations: list[Reservation],
    *,
    sync_param: str,
) -> None:
    if sync_param == "0":
        return
    for reservation in reservations:
        if reservation.import_source != "channex":
            continue
        if not parse_channex_booking_id(reservation.external_id):
            continue
        has_channex = ChannexMessage.objects.filter(reservation=reservation).exists()
        if sync_param == "auto" and has_channex:
            continue
        try:
            list_messages_for_reservation(
                integration,
                reservation,
                sync_if_empty=sync_param == "auto",
                force_sync=sync_param == "1",
            )
        except (ChannexBookingIngestError, ChannexApiError):
            continue


def _parse_timeline_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def _needs_reply(last: dict, reply_dismissed_at: datetime | None) -> bool:
    if last.get("direction") != "inbound":
        return False
    if reply_dismissed_at is None:
        return True
    last_at = _parse_timeline_datetime(last.get("created_at"))
    if last_at is None:
        return True
    dismissed = reply_dismissed_at
    if timezone.is_naive(dismissed):
        dismissed = timezone.make_aware(dismissed)
    return last_at > dismissed


def _serialize_thread(
    reservation: Reservation,
    last: dict,
    *,
    reply_dismissed_at: datetime | None = None,
) -> dict[str, Any]:
    preview = (last.get("body_text") or "").strip()
    if len(preview) > 200:
        preview = preview[:197] + "..."
    today = tenant_local_now(reservation.tenant).date()
    return {
        "reservation_id": reservation.pk,
        "booker_name": reservation.booker_name or "",
        "check_in": reservation.check_in.isoformat() if reservation.check_in else None,
        "check_out": reservation.check_out.isoformat() if reservation.check_out else None,
        "room_name": _room_name_for_reservation(reservation),
        "status": reservation.status,
        "arrives_today": reservation.check_in == today if reservation.check_in else False,
        "last_message_at": last.get("created_at"),
        "last_message_preview": preview,
        "last_channel": last.get("channel") or "",
        "last_direction": last.get("direction") or "",
        "needs_reply": _needs_reply(last, reply_dismissed_at),
    }


def list_message_threads_for_tenant(
    tenant: Tenant,
    *,
    integration: IntegrationConfig | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    needs_reply_only: bool = False,
    arriving_today_only: bool = False,
    sync_param: str = "auto",
) -> tuple[list[dict[str, Any]], int, int]:
    """Return (threads, total, needs_reply_count)."""
    reservation_ids = _reservation_ids_with_messages(tenant)
    if not reservation_ids:
        return [], 0, 0

    reservations = list(
        Reservation.objects.filter(tenant=tenant, pk__in=reservation_ids)
        .select_related("property")
        .prefetch_related("units", "units__unit")
        .order_by("-updated_at")
    )

    if integration is not None and sync_param in ("auto", "1"):
        _sync_channex_for_reservations(integration, reservations, sync_param=sync_param)

    reservation_pks = [r.pk for r in reservations]
    dismissed_map = {
        row.reservation_id: row.reply_dismissed_at
        for row in GuestMessageThreadState.objects.filter(
            tenant=tenant,
            reservation_id__in=reservation_pks,
        )
    }

    threads: list[dict[str, Any]] = []
    needs_reply_count = 0
    for reservation in reservations:
        last = last_timeline_entry(reservation)
        if last is None:
            continue
        row = _serialize_thread(
            reservation,
            last,
            reply_dismissed_at=dismissed_map.get(reservation.pk),
        )
        if row["needs_reply"]:
            needs_reply_count += 1
        if needs_reply_only and not row["needs_reply"]:
            continue
        if arriving_today_only and not row["arrives_today"]:
            continue
        threads.append(row)

    threads.sort(
        key=lambda t: t.get("last_message_at") or "",
        reverse=True,
    )

    total = len(threads)
    offset = max(page - 1, 0) * page_size
    page_rows = threads[offset : offset + page_size]
    return page_rows, total, needs_reply_count
