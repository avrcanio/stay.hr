from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.smoobu.booking_service import sync_smoobu_reservations
from apps.integrations.smoobu.exceptions import (
    SmoobuApiError,
    SmoobuBookingIngestError,
    SmoobuConfigError,
    SmoobuRatesError,
)
from apps.integrations.smoobu.reservation_blocking_service import (
    remove_reservation_smoobu_blocks,
    sync_reservation_smoobu_blocks,
)
from apps.integrations.smoobu.resolver import get_active_smoobu_integration
from apps.reservations.models import Reservation
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
    reservation = (
        Reservation.objects.filter(pk=reservation_id)
        .select_related("tenant")
        .first()
    )
    if reservation is None:
        logger.warning(
            "smoobu reservation block skipped: reservation id=%s not found",
            reservation_id,
        )
        return {"skipped": True, "reason": "not_found", "reservation_id": reservation_id}

    try:
        if action == "remove":
            result = remove_reservation_smoobu_blocks(reservation)
        else:
            result = sync_reservation_smoobu_blocks(reservation)
        logger.info(
            "smoobu reservation block task completed",
            extra={"reservation_id": reservation_id, "action": action, "result": result},
        )
        return result
    except (SmoobuConfigError, SmoobuRatesError) as exc:
        logger.warning(
            "smoobu reservation block skipped",
            extra={"reservation_id": reservation_id, "action": action, "reason": str(exc)},
        )
        return {"skipped": True, "reason": str(exc), "reservation_id": reservation_id}
    except SmoobuApiError as exc:
        logger.warning(
            "smoobu reservation block api error",
            extra={"reservation_id": reservation_id, "action": action, "error": str(exc)},
        )
        raise self.retry(exc=exc) from exc
    except Exception as exc:
        logger.exception(
            "smoobu reservation block task failed",
            extra={"reservation_id": reservation_id, "action": action},
        )
        raise self.retry(exc=exc) from exc
