from __future__ import annotations

import logging
from typing import Any

from apps.integrations.channex.booking_service import process_channex_booking_webhook
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.message_service import process_channex_message_webhook
from apps.integrations.channex.webhook_auth import webhook_secret_from_env
from apps.integrations.models import IntegrationConfig
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


def resolve_webhook_secret(
    integration_row: IntegrationConfig | None,
    config_secret: str,
) -> str:
    if config_secret:
        return config_secret
    if integration_row is not None:
        data = integration_row.get_config_dict()
        secret = str(data.get("webhook_secret") or "").strip()
        if secret:
            return secret
    return webhook_secret_from_env()


def find_channex_integration_for_property(
    property_id: str,
) -> tuple[IntegrationConfig | None, str]:
    rows = IntegrationConfig.objects.filter(
        provider=IntegrationConfig.Provider.CHANNEX,
        is_active=True,
    ).select_related("tenant", "property")

    if property_id:
        for row in rows:
            cfg = ChannexRuntimeConfig.from_integration_dict(row.get_config_dict())
            if cfg.property_id == property_id:
                secret = str(row.get_config_dict().get("webhook_secret") or "")
                return row, secret
        logger.error(
            "channex webhook property_id has no IntegrationConfig",
            extra={"property_id": property_id},
        )
        return None, ""

    return None, ""


def record_channex_webhook(
    *,
    integration_row: IntegrationConfig | None,
    tenant: Tenant | None,
    event: str,
    property_id: str,
    body: dict[str, Any],
) -> None:
    payload = body.get("payload")
    revision_id = ""
    booking_id = ""
    if isinstance(payload, dict):
        revision_id = str(payload.get("revision_id") or "")
        booking_id = str(payload.get("booking_id") or "")

    logger.info(
        "channex webhook received",
        extra={
            "tenant_slug": tenant.slug if tenant else None,
            "event": event,
            "property_id": property_id,
            "booking_id": booking_id,
            "revision_id": revision_id,
        },
    )

    if event == "message":
        if integration_row is None:
            logger.error(
                "channex message webhook without matching IntegrationConfig",
                extra={"property_id": property_id},
            )
            raise ChannexBookingIngestError("No Channex IntegrationConfig for property.")
        try:
            process_channex_message_webhook(
                integration_row,
                property_id=property_id,
                body=body,
            )
        except ChannexBookingIngestError:
            logger.exception(
                "channex message ingest failed",
                extra={"property_id": property_id, "booking_id": booking_id},
            )
            raise
        return

    if not event.startswith("booking"):
        return

    if integration_row is None:
        logger.error(
            "channex booking webhook without matching IntegrationConfig",
            extra={"property_id": property_id, "revision_id": revision_id},
        )
        raise ChannexBookingIngestError("No Channex IntegrationConfig for property.")

    try:
        process_channex_booking_webhook(
            integration_row,
            revision_id=revision_id,
            booking_id=booking_id,
            event=event,
        )
    except (ChannexApiError, ChannexBookingIngestError):
        logger.exception(
            "channex booking ingest failed",
            extra={"revision_id": revision_id, "booking_id": booking_id, "event": event},
        )
        raise
