# Migration B — backfill provider_message_id from WhatsAppMessage where possible

from __future__ import annotations

from django.db import migrations


def _best_whatsapp_match(outbound, WhatsAppMessage):
    """Pick the outbound WhatsAppMessage that best matches this GuestOutboundMessage."""
    candidates = WhatsAppMessage.objects.filter(
        tenant_id=outbound.tenant_id,
        reservation_id=outbound.reservation_id,
        direction="outbound",
    ).order_by("created_at")

    body = (outbound.body_text or "").strip()
    if body:
        exact = candidates.filter(body=body).order_by("-created_at").first()
        if exact and exact.wamid:
            return exact

    outbound_created = outbound.created_at
    best = None
    best_delta = None
    for wa_msg in candidates:
        if not wa_msg.wamid:
            continue
        delta = abs((wa_msg.created_at - outbound_created).total_seconds())
        if best is None or delta < best_delta:
            best = wa_msg
            best_delta = delta
    if best is not None and best_delta is not None and best_delta <= 300:
        return best
    return None


def backfill_provider_message_ids(apps, schema_editor):
    GuestOutboundMessage = apps.get_model("communications", "GuestOutboundMessage")
    WhatsAppMessage = apps.get_model("integrations", "WhatsAppMessage")

    qs = GuestOutboundMessage.objects.filter(
        channel="whatsapp",
        status="sent",
        provider_message_id="",
    ).select_related("reservation")

    for outbound in qs.iterator():
        wa_msg = _best_whatsapp_match(outbound, WhatsAppMessage)
        if wa_msg and wa_msg.wamid:
            GuestOutboundMessage.objects.filter(pk=outbound.pk).update(
                provider="meta",
                provider_message_id=wa_msg.wamid,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0010_guestoutbound_whatsapp_fields"),
        ("integrations", "0025_channexbookingrevision_nullable_reservation"),
    ]

    operations = [
        migrations.RunPython(backfill_provider_message_ids, migrations.RunPython.noop),
    ]
