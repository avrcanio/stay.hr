from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.channel_manager.dispatch import (
    confirm_web_booking_if_ready,
    sync_reservation_outbound,
)
from apps.integrations.smoobu.error_classification import is_smoobu_block_conflict
from apps.integrations.smoobu.exceptions import (
    SmoobuApiError,
    SmoobuConfigError,
    SmoobuRatesError,
)
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channel_manager.resolver import get_channel_manager
from apps.reservations.booking_lifecycle import is_web_pending_booking, refuse_web_booking
from apps.reservations.models import Reservation
from apps.tenants.models import ChannelManager

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_reservation_outbound_task(
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
            "outbound reservation sync skipped: reservation id=%s not found",
            reservation_id,
        )
        return {"skipped": True, "reason": "not_found", "reservation_id": reservation_id}

    web_pending = is_web_pending_booking(reservation)
    manager = get_channel_manager(reservation.tenant)

    try:
        result = sync_reservation_outbound(reservation, action=action)
        if action != "remove" and web_pending:
            confirm_web_booking_if_ready(reservation_id, result)

        logger.info(
            "outbound reservation sync completed",
            extra={
                "reservation_id": reservation_id,
                "action": action,
                "channel_manager": manager,
                "result": result,
            },
        )
        return result
    except (SmoobuConfigError, SmoobuRatesError) as exc:
        if web_pending and manager == ChannelManager.SMOOBU and is_smoobu_block_conflict(exc):
            refuse_web_booking(reservation_id, reason=str(exc))
            return {"refused": True, "reason": str(exc), "reservation_id": reservation_id}
        logger.warning(
            "outbound reservation sync skipped",
            extra={"reservation_id": reservation_id, "action": action, "reason": str(exc)},
        )
        return {"skipped": True, "reason": str(exc), "reservation_id": reservation_id}
    except SmoobuApiError as exc:
        if web_pending and manager == ChannelManager.SMOOBU and is_smoobu_block_conflict(exc):
            refuse_web_booking(reservation_id, reason=str(exc))
            return {"refused": True, "reason": str(exc), "reservation_id": reservation_id}
        logger.warning(
            "outbound reservation sync api error",
            extra={"reservation_id": reservation_id, "action": action, "error": str(exc)},
        )
        raise self.retry(exc=exc) from exc
    except (ChannexApiError, ChannexBookingIngestError) as exc:
        if web_pending and manager == ChannelManager.CHANNEX:
            refuse_web_booking(reservation_id, reason=str(exc))
            return {"refused": True, "reason": str(exc), "reservation_id": reservation_id}
        logger.warning(
            "channex outbound sync skipped",
            extra={"reservation_id": reservation_id, "action": action, "reason": str(exc)},
        )
        return {"skipped": True, "reason": str(exc), "reservation_id": reservation_id}
    except Exception as exc:
        logger.exception(
            "outbound reservation sync failed",
            extra={"reservation_id": reservation_id, "action": action},
        )
        raise self.retry(exc=exc) from exc
