from __future__ import annotations

from celery import shared_task

from apps.integrations.whatsapp.whatsapp_document_batch import on_whatsapp_document_received


@shared_task
def process_whatsapp_document_message(message_id: int) -> dict:
    """Routes inbound WhatsApp media into the debounced document batch flow."""
    return on_whatsapp_document_received(message_id)
