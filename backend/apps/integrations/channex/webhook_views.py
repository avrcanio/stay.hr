from __future__ import annotations

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.webhook_auth import extract_event_name, verify_channex_webhook_request
from apps.integrations.channex.webhook_service import (
    find_channex_integration_for_property,
    record_channex_webhook,
    resolve_webhook_secret,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class ChannexWebhookView(APIView):
    """
    Inbound Channex webhooks (booking, ARI, etc.).

    Secured via custom header + query params configured in Channex UI.
  """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        property_id = str(body.get("property_id") or request.query_params.get("property_id") or "")

        integration_row, config_secret = find_channex_integration_for_property(property_id)
        secret = resolve_webhook_secret(integration_row, config_secret)

        if not verify_channex_webhook_request(request, config_secret=secret):
            logger.warning(
                "channex webhook rejected",
                extra={"property_id": property_id, "event": extract_event_name(body)},
            )
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        event = extract_event_name(body)
        try:
            record_channex_webhook(
                integration_row=integration_row,
                tenant=integration_row.tenant if integration_row else None,
                event=event,
                property_id=property_id,
                body=body,
            )
        except (ChannexApiError, ChannexBookingIngestError) as exc:
            return Response(
                {"status": "error", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"status": "ok", "event": event}, status=status.HTTP_200_OK)

    def get(self, request):
        """Allow HEAD/GET health checks from Channex test tool."""
        if not verify_channex_webhook_request(request, config_secret=resolve_webhook_secret(None, "")):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
