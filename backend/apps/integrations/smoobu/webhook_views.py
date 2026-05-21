from __future__ import annotations

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.smoobu.exceptions import SmoobuBookingIngestError
from apps.integrations.smoobu.webhook_auth import verify_smoobu_webhook_request, webhook_secret_from_env
from apps.integrations.smoobu.webhook_service import (
    extract_action,
    find_smoobu_integration,
    record_smoobu_webhook,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class SmoobuWebhookView(APIView):
    """Inbound Smoobu webhooks (reservations). Secured via shared secret."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def _config_secret(self, integration_row) -> str:
        if integration_row is None:
            return ""
        return str(integration_row.get_config_dict().get("webhook_secret") or "")

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        integration_row = find_smoobu_integration()
        config_secret = self._config_secret(integration_row)

        if not verify_smoobu_webhook_request(request, config_secret=config_secret):
            logger.warning(
                "smoobu webhook rejected",
                extra={"action": extract_action(body)},
            )
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        if integration_row is None:
            return Response(
                {"detail": "No active Smoobu integration"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        action = extract_action(body)
        try:
            result = record_smoobu_webhook(
                integration_row=integration_row,
                action=action,
                body=body,
            )
        except SmoobuBookingIngestError as exc:
            return Response(
                {"status": "error", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(result, status=status.HTTP_200_OK)

    def get(self, request):
        integration_row = find_smoobu_integration()
        config_secret = self._config_secret(integration_row)
        secret = config_secret or webhook_secret_from_env()
        if secret and not verify_smoobu_webhook_request(request, config_secret=config_secret):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
