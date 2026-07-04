from __future__ import annotations

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_views import ReceptionReadView, ReceptionWriteView
from apps.integrations.whatsapp.integration_service import (
    create_whatsapp_template,
    exchange_oauth_code,
    get_whatsapp_integration_status,
    list_cached_templates,
    sync_templates_from_meta,
    upsert_whatsapp_integration,
)
from apps.integrations.whatsapp.meta_templates import MetaTemplateApiError
from apps.integrations.whatsapp.welcome_template_definitions import FOOTER


class WhatsAppConnectSerializer(serializers.Serializer):
    waba_id = serializers.CharField(max_length=64)
    phone_number_id = serializers.CharField(max_length=64)
    code = serializers.CharField(required=False, allow_blank=True, default="")
    access_token = serializers.CharField(required=False, allow_blank=True, default="")


class WhatsAppTemplateCreateSerializer(serializers.Serializer):
    name = serializers.RegexField(regex=r"^[a-z0-9_]+$", max_length=512)
    language = serializers.CharField(max_length=8)
    category = serializers.ChoiceField(
        choices=["MARKETING", "UTILITY", "AUTHENTICATION"],
        default="MARKETING",
    )
    body_text = serializers.CharField()
    button_text = serializers.CharField(required=False, allow_blank=True, default="")
    header_image_url = serializers.URLField(required=False, allow_blank=True, default="")


class ReceptionWhatsAppIntegrationView(ReceptionReadView, APIView):
    def get(self, request):
        return Response(get_whatsapp_integration_status(tenant=request.tenant))


class ReceptionWhatsAppConnectView(ReceptionWriteView, APIView):
    def post(self, request):
        serializer = WhatsAppConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        code = (data.get("code") or "").strip()
        access_token = (data.get("access_token") or "").strip()

        if code:
            try:
                access_token = exchange_oauth_code(code=code)
            except ValueError as exc:
                raise ValidationError({"code": str(exc)}) from exc
        elif access_token:
            if not settings.DEBUG and not getattr(settings, "ALLOW_WHATSAPP_CONNECT_TOKEN", False):
                raise ValidationError(
                    {"access_token": "Manual token connect is disabled in production."}
                )
        else:
            raise ValidationError({"code": "Provide code or access_token."})

        upsert_whatsapp_integration(
            tenant=request.tenant,
            waba_id=data["waba_id"],
            phone_number_id=data["phone_number_id"],
        )
        return Response(get_whatsapp_integration_status(tenant=request.tenant))


class ReceptionWhatsAppTemplatesView(ReceptionReadView, APIView):
    def get(self, request):
        live = request.query_params.get("live", "").strip().lower() in ("1", "true", "yes")
        try:
            payload = list_cached_templates(tenant=request.tenant, live=live)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(payload)

    def post(self, request):
        serializer = WhatsAppTemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        body = (data["body_text"] or "").strip()
        if FOOTER not in body:
            body = f"{body}\n\n{FOOTER}"

        components: list[dict] = [{"type": "BODY", "text": body}]
        button_text = (data.get("button_text") or "").strip()
        if button_text:
            components.append(
                {
                    "type": "BUTTONS",
                    "buttons": [{"type": "QUICK_REPLY", "text": button_text[:25]}],
                }
            )

        payload = {
            "name": data["name"],
            "language": data["language"],
            "category": data["category"],
            "components": components,
        }

        try:
            result = create_whatsapp_template(tenant=request.tenant, payload=payload)
        except MetaTemplateApiError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        return Response(result, status=status.HTTP_201_CREATED)


class ReceptionWhatsAppTemplatesSyncView(ReceptionWriteView, APIView):
    def post(self, request):
        try:
            payload = sync_templates_from_meta(tenant=request.tenant)
        except MetaTemplateApiError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(payload)
