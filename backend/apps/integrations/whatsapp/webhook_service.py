from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
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

    if WhatsAppMessage.objects.filter(wamid=parsed.wamid).exists():
        return {"status": "duplicate", "wamid": parsed.wamid}

    row = WhatsAppMessage.objects.create(
        tenant_id=integration_row.tenant_id,
        integration=integration_row,
        wamid=parsed.wamid,
        wa_id=parsed.wa_id,
        phone_number_id=parsed.phone_number_id,
        direction=WhatsAppMessage.Direction.INBOUND,
        message_type=parsed.message_type,
        body=parsed.body,
        raw_payload=parsed.raw_message,
    )
    process_inbound_message.delay(row.pk, profile_name=parsed.profile_name)
    return {"status": "queued", "message_id": row.pk, "wamid": parsed.wamid}


def process_whatsapp_webhook(body: dict[str, Any]) -> dict[str, Any]:
    parsed_messages = extract_inbound_messages(body)
    if not parsed_messages:
        return {"status": "ok", "processed": 0}

    results: list[dict[str, Any]] = []
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
