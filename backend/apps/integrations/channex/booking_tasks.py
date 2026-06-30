from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.channex.booking_service import process_channex_booking_revisions_feed
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.models import IntegrationConfig

logger = logging.getLogger(__name__)


@shared_task
def process_channex_booking_revisions_feed_periodic(
    *,
    tenant_slug: str = "uzorita",
) -> dict:
    """Process non-acknowledged Channex booking revisions (missed webhook fallback)."""
    row = (
        IntegrationConfig.objects.filter(
            tenant__slug=tenant_slug,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        .select_related("tenant")
        .first()
    )
    if row is None:
        return {"processed": 0, "error": "no_integration"}

    try:
        result = process_channex_booking_revisions_feed(row)
    except (ChannexBookingIngestError, ChannexApiError) as exc:
        logger.warning(
            "channex booking revisions feed periodic failed",
            extra={"tenant_slug": tenant_slug, "error": str(exc)},
        )
        return {"processed": 0, "error": str(exc)}

    reservations = result["ingested"]
    ack_only = int(result.get("ack_only") or 0)
    errors = int(result.get("errors") or 0)
    reservation_ids = [r.pk for r in reservations]
    if reservation_ids or ack_only:
        logger.info(
            "channex booking revisions feed periodic processed",
            extra={
                "tenant_slug": tenant_slug,
                "reservation_ids": reservation_ids,
                "ack_only": ack_only,
                "errors": errors,
            },
        )
    return {
        "processed": len(reservation_ids),
        "ack_only": ack_only,
        "errors": errors,
        "reservation_ids": reservation_ids,
    }
