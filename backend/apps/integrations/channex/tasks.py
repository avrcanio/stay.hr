from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.channex.ari_service import flush_channex_ari_outbox, get_active_channex_integration
from apps.integrations.channex.exceptions import ChannexBookingIngestError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_reservation_channex_availability_task(
    self,
    reservation_id: int,
    action: str = "sync",
) -> dict:
    from apps.integrations.channel_manager.tasks import sync_reservation_outbound_task

    return sync_reservation_outbound_task(reservation_id, action)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def flush_channex_ari_outbox_task(self, tenant_slug: str = "demo") -> list[dict]:
    try:
        integration = get_active_channex_integration(tenant_slug)
        results = flush_channex_ari_outbox(integration)
        logger.info(
            "channex ari outbox flushed",
            extra={"tenant_slug": tenant_slug, "results": results},
        )
        return results
    except ChannexBookingIngestError as exc:
        logger.warning("channex ari flush skipped: %s", exc)
        return []
    except Exception as exc:
        logger.exception("channex ari flush failed")
        raise self.retry(exc=exc) from exc
