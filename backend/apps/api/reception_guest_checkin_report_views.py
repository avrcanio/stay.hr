"""Reception guest web check-in ops / analytics report."""

from __future__ import annotations

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from apps.api.reception_views import ReceptionReadView
from apps.properties.resolution import PropertyResolutionError, resolve_property_for_tenant
from apps.reservations.guest_checkin_analytics import (
    active_checkin_sessions_for_property,
    guest_checkin_kpis_to_dict,
    load_guest_checkin_kpis,
)


class GuestCheckInReportView(ReceptionReadView):
    """KPI snapshot + active sessions for property ops dashboard."""

    def get(self, request):
        property_slug = (request.query_params.get("property_slug") or "").strip()
        days_raw = (request.query_params.get("days") or "").strip()
        try:
            days = max(1, int(days_raw)) if days_raw else int(
                getattr(settings, "GUEST_CHECKIN_METRICS_DAYS", 30)
            )
        except ValueError:
            return Response({"code": "days_invalid"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            prop = resolve_property_for_tenant(request.tenant, slug=property_slug)
        except PropertyResolutionError as exc:
            message = exc.message if hasattr(exc, "message") else str(exc)
            if isinstance(message, dict):
                detail = next(iter(message.values()), str(message))
                if isinstance(detail, list):
                    detail = detail[0] if detail else str(message)
            else:
                detail = str(message)
            return Response(
                {"code": "property_required", "detail": str(detail)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        kpis = load_guest_checkin_kpis(
            days=days,
            tenant=request.tenant,
            property=prop,
        )
        active_sessions = active_checkin_sessions_for_property(
            tenant=request.tenant,
            property=prop,
        )
        return Response(
            {
                "property_slug": prop.slug,
                "property_name": prop.name,
                "kpis": guest_checkin_kpis_to_dict(kpis),
                "active_sessions": active_sessions,
            }
        )
