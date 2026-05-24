from __future__ import annotations

import json
import logging

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.whatsapp.webhook_auth import (
    verify_webhook_signature,
    verify_webhook_subscription,
)
from apps.integrations.whatsapp.webhook_service import process_whatsapp_webhook

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(APIView):
    """Meta WhatsApp Cloud API webhook (verify + inbound messages)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        challenge = verify_webhook_subscription(request)
        if challenge is None:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return HttpResponse(challenge, content_type="text/plain")

    def post(self, request):
        raw_body = request.body or b""
        if not verify_webhook_signature(request, raw_body=raw_body):
            logger.warning("whatsapp webhook rejected: invalid signature")
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(body, dict):
            return Response({"detail": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)

        result = process_whatsapp_webhook(body)
        return Response(result, status=status.HTTP_200_OK)
