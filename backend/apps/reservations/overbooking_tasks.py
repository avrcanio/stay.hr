from __future__ import annotations

import logging
from datetime import date

from celery import shared_task

from apps.reservations.overbooking import find_conflicts
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


def _notify_overbooking_conflicts(tenant: Tenant, conflicts: list) -> None:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data

    lines = []
    for conflict in conflicts[:5]:
        incumbent = conflict.incumbent.booking_code or conflict.incumbent.pk
        conflicting = conflict.conflicting.booking_code or conflict.conflicting.pk
        lines.append(
            f"{conflict.unit.code} {conflict.overlap_from}: "
            f"{incumbent} vs {conflicting}"
        )
    if len(conflicts) > 5:
        lines.append(f"+{len(conflicts) - 5} još")

    body = "; ".join(lines)
    data = reception_push_data(
        event_type="reservation.overbooking_detected",
        reservation_id=conflicts[0].conflicting.pk,
        summary=body,
        booking_code="",
        check_in=conflicts[0].overlap_from.isoformat(),
        check_out=conflicts[0].overlap_to.isoformat(),
        status="",
        tenant_id=str(tenant.pk),
    )
    send_tenant_reception_push(
        tenant_id=tenant.pk,
        title=f"Overbooking ({len(conflicts)})",
        body=body,
        data=data,
    )


@shared_task
def detect_overbooking_daily(tenant_id: int = 2) -> dict:
    """Daily scan for unit overlaps; alerts reception when conflicts exist."""
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return {"skipped": True, "reason": "tenant_not_found", "tenant_id": tenant_id}

    from_date = date.today()
    conflicts = find_conflicts(tenant=tenant, from_date=from_date)

    if conflicts:
        _notify_overbooking_conflicts(tenant, conflicts)
        logger.warning(
            "overbooking conflicts detected",
            extra={"tenant_id": tenant_id, "count": len(conflicts)},
        )

    return {
        "tenant_id": tenant_id,
        "from_date": from_date.isoformat(),
        "conflict_count": len(conflicts),
    }
