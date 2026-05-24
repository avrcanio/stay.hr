from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.smoobu.booking_service import sync_smoobu_reservations
from apps.integrations.smoobu.exceptions import SmoobuBookingIngestError, SmoobuConfigError
from apps.integrations.smoobu.resolver import get_active_smoobu_integration
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

UZORITA_TENANT_ID = 2


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_smoobu_reservations_task(self, tenant_id: int = UZORITA_TENANT_ID) -> dict:
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        logger.warning("smoobu sync skipped: tenant id=%s not found", tenant_id)
        return {"skipped": True, "reason": "tenant_not_found", "tenant_id": tenant_id}

    try:
        integration = get_active_smoobu_integration(tenant.slug)
        stats = sync_smoobu_reservations(integration)
        logger.info(
            "smoobu reservations synced",
            extra={"tenant_slug": tenant.slug, "stats": stats},
        )
        return stats
    except (SmoobuConfigError, SmoobuBookingIngestError) as exc:
        logger.warning("smoobu sync skipped: %s", exc)
        return {"skipped": True, "reason": str(exc), "tenant_id": tenant_id}
    except Exception as exc:
        logger.exception("smoobu sync failed")
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_reservation_smoobu_blocks_task(
    self,
    reservation_id: int,
    action: str = "sync",
) -> dict:
    from apps.integrations.channel_manager.tasks import sync_reservation_outbound_task

    return sync_reservation_outbound_task(reservation_id, action)
