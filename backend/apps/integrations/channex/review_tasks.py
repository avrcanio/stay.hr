from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.review_service import (
    mark_reviews_synced,
    repair_channex_review_replies,
    relink_unlinked_channex_reviews,
    sync_reviews_from_channex,
)
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task
def sync_channex_reviews_periodic(*, tenant_slug: str = "uzorita", max_pages: int = 10) -> dict:
    """Pull guest reviews from Channex (Booking.com, Airbnb, etc.)."""
    result = {"synced": 0, "relinked": 0, "repaired": 0, "failed": 0}

    tenant = Tenant.objects.filter(slug=tenant_slug).first()
    if tenant is None:
        return {**result, "error": "tenant_not_found"}

    try:
        integration = get_active_channex_integration(tenant_slug)
    except ChannexBookingIngestError as exc:
        return {**result, "error": str(exc)}

    try:
        rows = sync_reviews_from_channex(integration, max_pages=max_pages)
        result["synced"] = len(rows)
        mark_reviews_synced(tenant.pk)
    except (ChannexBookingIngestError, ChannexApiError) as exc:
        result["failed"] = 1
        logger.warning(
            "channex periodic review sync failed",
            extra={"tenant_slug": tenant_slug, "error": str(exc)},
        )
        return {**result, "error": str(exc)}

    result["relinked"] = relink_unlinked_channex_reviews(tenant)
    result["repaired"] = repair_channex_review_replies(tenant)
    return result
