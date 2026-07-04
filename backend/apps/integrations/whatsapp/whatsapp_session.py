from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.integrations.models import WhatsAppMessage
from apps.integrations.whatsapp.phone import normalize_phone
from apps.reservations.models import Reservation


def is_customer_service_window_open(
    *,
    tenant_id: int,
    reservation: Reservation,
    phone_wa: str | None = None,
) -> bool:
    """True when guest sent inbound WhatsApp within the 24h customer-care window."""
    wa_id = (phone_wa or "").strip() or normalize_phone(
        (reservation.booker_phone or "").strip()
    )
    if not wa_id:
        return False
    cutoff = timezone.now() - timedelta(hours=24)
    return (
        WhatsAppMessage.objects.filter(
            tenant_id=tenant_id,
            direction=WhatsAppMessage.Direction.INBOUND,
            created_at__gte=cutoff,
        )
        .filter(Q(reservation=reservation) | Q(wa_id=wa_id))
        .exists()
    )


def resolved_tenant_id_for_message(message: WhatsAppMessage) -> int:
    routing = getattr(message, "inbound_routing", None)
    if routing is not None and routing.resolved_tenant_id:
        return routing.resolved_tenant_id
    return message.tenant_id
