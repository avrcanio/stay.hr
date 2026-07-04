from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError

from apps.communications.models import GuestOutboundDeliveryStatus, GuestOutboundMessage
from apps.integrations.models import IntegrationConfig, WhatsAppInboundRouting, WhatsAppMessage
from apps.integrations.whatsapp.platform_inbound_router import route_inbound_message
from apps.integrations.whatsapp.tasks import process_inbound_message

from apps.integrations.whatsapp.media_download import extract_media_from_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedInboundMessage:
    phone_number_id: str
    wa_id: str
    wamid: str
    message_type: str
    body: str
    profile_name: str
    raw_message: dict[str, Any]


def extract_inbound_messages(body: dict[str, Any]) -> list[ParsedInboundMessage]:
    if body.get("object") != "whatsapp_business_account":
        return []

    messages: list[ParsedInboundMessage] = []
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            contacts = {
                str(contact.get("wa_id") or "").strip(): str(
                    (contact.get("profile") or {}).get("name") or ""
                ).strip()
                for contact in value.get("contacts") or []
            }
            for message in value.get("messages") or []:
                wa_id = str(message.get("from") or "").strip()
                wamid = str(message.get("id") or "").strip()
                message_type = str(message.get("type") or "").strip() or "unknown"
                text_body = ""
                if message_type == "text":
                    text_body = str((message.get("text") or {}).get("body") or "").strip()
                elif message_type == "interactive":
                    interactive = message.get("interactive") or {}
                    interactive_type = str(interactive.get("type") or "").strip()
                    if interactive_type == "button_reply":
                        text_body = str(
                            (interactive.get("button_reply") or {}).get("title") or ""
                        ).strip()
                    elif interactive_type == "list_reply":
                        text_body = str(
                            (interactive.get("list_reply") or {}).get("title") or ""
                        ).strip()
                elif message_type == "button":
                    button = message.get("button") or {}
                    text_body = str(button.get("text") or button.get("payload") or "").strip()
                else:
                    _, _, caption = extract_media_from_message(message)
                    text_body = caption
                messages.append(
                    ParsedInboundMessage(
                        phone_number_id=phone_number_id,
                        wa_id=wa_id,
                        wamid=wamid,
                        message_type=message_type,
                        body=text_body,
                        profile_name=contacts.get(wa_id, ""),
                        raw_message=message,
                    )
                )
    return messages


def record_inbound_whatsapp_message(
    *,
    integration_row: IntegrationConfig,
    parsed: ParsedInboundMessage,
) -> dict[str, Any]:
    if not parsed.wamid:
        return {"status": "ignored", "reason": "missing_wamid"}

    try:
        row, created = WhatsAppMessage.objects.get_or_create(
            wamid=parsed.wamid,
            defaults={
                "tenant_id": integration_row.tenant_id,
                "integration": integration_row,
                "wa_id": parsed.wa_id,
                "phone_number_id": parsed.phone_number_id,
                "direction": WhatsAppMessage.Direction.INBOUND,
                "message_type": parsed.message_type,
                "body": parsed.body,
                "raw_payload": parsed.raw_message,
            },
        )
    except IntegrityError:
        return {"status": "duplicate", "wamid": parsed.wamid}

    if not created:
        return {"status": "duplicate", "wamid": parsed.wamid}

    routing = route_inbound_message(message=row, integration=integration_row)
    process_inbound_message.delay(row.pk, profile_name=parsed.profile_name)
    return {
        "status": "queued",
        "message_id": row.pk,
        "wamid": parsed.wamid,
        "routing_status": routing.status,
    }


def extract_status_updates(body: dict[str, Any]) -> list[dict[str, str]]:
    if body.get("object") != "whatsapp_business_account":
        return []
    updates: list[dict[str, str]] = []
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for item in value.get("statuses") or []:
                wamid = str(item.get("id") or "").strip()
                status = str(item.get("status") or "").strip().lower()
                if wamid and status:
                    updates.append({"wamid": wamid, "status": status})
    return updates


def apply_outbound_status_update(*, wamid: str, status: str) -> dict[str, Any]:
    mapping = {
        "sent": GuestOutboundDeliveryStatus.SENT,
        "delivered": GuestOutboundDeliveryStatus.DELIVERED,
        "read": GuestOutboundDeliveryStatus.READ,
        "failed": GuestOutboundDeliveryStatus.FAILED,
    }
    delivery_status = mapping.get(status)
    if not delivery_status:
        return {"status": "ignored", "wamid": wamid}

    updated = GuestOutboundMessage.objects.filter(provider_message_id=wamid).update(
        delivery_status=delivery_status,
    )
    if updated:
        return {"status": "updated", "wamid": wamid, "delivery_status": delivery_status}
    return {"status": "not_found", "wamid": wamid}


def process_whatsapp_webhook(body: dict[str, Any]) -> dict[str, Any]:
    status_updates = extract_status_updates(body)
    status_results = [apply_outbound_status_update(**item) for item in status_updates]

    parsed_messages = extract_inbound_messages(body)
    if not parsed_messages:
        return {
            "status": "ok",
            "processed": len(status_results),
            "status_results": status_results,
        }

    results: list[dict[str, Any]] = list(status_results)
    for parsed in parsed_messages:
        integration_row = None
        if parsed.phone_number_id:
            from apps.integrations.whatsapp.resolver import find_whatsapp_integration

            integration_row = find_whatsapp_integration(parsed.phone_number_id)
        if integration_row is None:
            logger.warning(
                "whatsapp webhook: no integration for phone_number_id=%s",
                parsed.phone_number_id,
            )
            results.append(
                {
                    "status": "unrouted",
                    "phone_number_id": parsed.phone_number_id,
                    "wamid": parsed.wamid,
                }
            )
            continue

        results.append(
            record_inbound_whatsapp_message(
                integration_row=integration_row,
                parsed=parsed,
            )
        )

    return {"status": "ok", "processed": len(results), "results": results}
