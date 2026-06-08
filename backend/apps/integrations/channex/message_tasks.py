from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.message_service import (
    _reservation_can_sync_messages,
    relink_unlinked_channex_messages,
    sync_booking_messages_from_channex,
)
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task
def sync_channex_messages_for_upcoming_checkins(*, tenant_slug: str = "uzorita") -> dict:
    """Pull Channex messages for reservations checking in today or tomorrow."""
    result = {"synced": 0, "skipped": 0, "failed": 0, "relinked": 0}

    tenant = Tenant.objects.filter(slug=tenant_slug).first()
    if tenant is None:
        return {**result, "error": "tenant_not_found"}

    try:
        integration = get_active_channex_integration(tenant_slug)
    except ChannexBookingIngestError as exc:
        return {**result, "error": str(exc)}

    result["relinked"] = relink_unlinked_channex_messages(tenant)

    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    reservations = Reservation.objects.filter(
        tenant=tenant,
        import_source="channex",
        check_in__in=[today, tomorrow],
        status=Reservation.Status.EXPECTED,
    ).select_related("property", "tenant")

    for reservation in reservations:
        if not _reservation_can_sync_messages(reservation):
            result["skipped"] += 1
            continue
        try:
            rows = sync_booking_messages_from_channex(integration, reservation)
            result["synced"] += len(rows)
        except (ChannexBookingIngestError, ChannexApiError) as exc:
            result["failed"] += 1
            logger.warning(
                "channex upcoming check-in message sync failed",
                extra={"reservation_id": reservation.pk, "error": str(exc)},
            )

    return result
