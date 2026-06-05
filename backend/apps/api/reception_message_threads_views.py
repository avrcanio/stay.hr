"""Reception guest message threads inbox API."""

from __future__ import annotations

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import DenyAdminScopes, HasReceptionAccess
from apps.api.views import TenantAPIView
from apps.communications.message_threads_service import (
    DEFAULT_PAGE_SIZE,
    list_message_threads_for_tenant,
)
from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError


class ReceptionMessageThreadsListView(TenantAPIView, APIView):
    permission_classes = [HasReceptionAccess, DenyAdminScopes]
    required_scopes = ["reception:read"]

    def get(self, request):
        sync_param = request.query_params.get("sync", "auto")
        page = max(int(request.query_params.get("page", 1) or 1), 1)
        page_size = min(
            max(int(request.query_params.get("page_size", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE), 1),
            100,
        )
        needs_reply_only = request.query_params.get("needs_reply", "") in ("1", "true", "yes")
        arriving_today_only = request.query_params.get("arriving_today", "") in ("1", "true", "yes")

        integration = None
        if sync_param in ("auto", "1"):
            try:
                integration = get_active_channex_integration(request.tenant.slug)
            except ChannexBookingIngestError:
                integration = None

        try:
            threads, total, needs_reply_count = list_message_threads_for_tenant(
                request.tenant,
                integration=integration,
                page=page,
                page_size=page_size,
                needs_reply_only=needs_reply_only,
                arriving_today_only=arriving_today_only,
                sync_param=sync_param,
            )
        except (ChannexBookingIngestError, ChannexApiError) as exc:
            raise ValidationError(str(exc)) from exc

        return Response(
            {
                "page": page,
                "page_size": page_size,
                "total": total,
                "needs_reply_count": needs_reply_count,
                "threads": threads,
            }
        )
