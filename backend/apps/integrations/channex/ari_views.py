from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import DenyAdminScopes, HasApiApplication, HasScope
from apps.api.views import TenantAPIView
from apps.integrations.channex.ari_service import (
    apply_availability_updates,
    apply_rate_updates,
    build_full_sync,
    get_active_channex_integration,
    push_channex_ari,
    seed_channel_rate_plans_from_config,
)
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.tasks import flush_channex_ari_outbox_task
from apps.integrations.models import ChannexAriOutbox


class RateUpdateItemSerializer(serializers.Serializer):
    unit_code = serializers.CharField()
    rate_plan_code = serializers.CharField()
    date = serializers.DateField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    rate = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    min_stay_arrival = serializers.IntegerField(required=False, min_value=1)
    min_stay_through = serializers.IntegerField(required=False, min_value=1)
    max_stay = serializers.IntegerField(required=False, min_value=0)
    stop_sell = serializers.BooleanField(required=False)
    closed_to_arrival = serializers.BooleanField(required=False)
    closed_to_departure = serializers.BooleanField(required=False)

    def validate(self, attrs):
        has_single = bool(attrs.get("date"))
        has_range = bool(attrs.get("date_from")) and bool(attrs.get("date_to"))
        if has_single == has_range:
            raise serializers.ValidationError("Provide either date or date_from + date_to.")
        has_value = attrs.get("rate") is not None or any(
            attrs.get(f) is not None
            for f in (
                "min_stay_arrival",
                "min_stay_through",
                "max_stay",
                "stop_sell",
                "closed_to_arrival",
                "closed_to_departure",
            )
        )
        if not has_value:
            raise serializers.ValidationError(
                "Provide at least one of rate or restriction fields."
            )
        return attrs


class AvailabilityUpdateItemSerializer(serializers.Serializer):
    unit_code = serializers.CharField()
    date = serializers.DateField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    availability = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        has_single = bool(attrs.get("date"))
        has_range = bool(attrs.get("date_from")) and bool(attrs.get("date_to"))
        if has_single == has_range:
            raise serializers.ValidationError("Provide either date or date_from + date_to.")
        return attrs


class ChannexAriRatesView(TenantAPIView, APIView):
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]
    required_scopes = ["reception:write"]

    def patch(self, request):
        serializer = RateUpdateItemSerializer(data=request.data.get("updates", []), many=True)
        serializer.is_valid(raise_exception=True)
        integration = get_active_channex_integration(request.tenant.slug)
        try:
            rows = apply_rate_updates(integration, serializer.validated_data)
            if request.query_params.get("async", "").lower() in {"1", "true", "yes"}:
                flush_channex_ari_outbox_task.delay(request.tenant.slug)
                pushed = []
            else:
                pushed = push_channex_ari(integration)
        except (ChannexApiError, ChannexBookingIngestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "updated_days": len(rows),
                "push_results": pushed,
            },
            status=status.HTTP_200_OK,
        )


class ChannexAriAvailabilityView(TenantAPIView, APIView):
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]
    required_scopes = ["reception:write"]

    def patch(self, request):
        serializer = AvailabilityUpdateItemSerializer(
            data=request.data.get("updates", []), many=True
        )
        serializer.is_valid(raise_exception=True)
        integration = get_active_channex_integration(request.tenant.slug)
        try:
            rows = apply_availability_updates(integration, serializer.validated_data)
            if request.query_params.get("async", "").lower() in {"1", "true", "yes"}:
                flush_channex_ari_outbox_task.delay(request.tenant.slug)
                pushed = []
            else:
                pushed = push_channex_ari(integration)
        except (ChannexApiError, ChannexBookingIngestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "updated_days": len(rows),
                "push_results": pushed,
            },
            status=status.HTTP_200_OK,
        )


class ChannexAriFullSyncView(TenantAPIView, APIView):
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]
    required_scopes = ["reception:write"]

    def post(self, request):
        integration = get_active_channex_integration(request.tenant.slug)
        seed_channel_rate_plans_from_config(integration)
        days = int(request.data.get("days") or 500)
        try:
            availability_values, restriction_values = build_full_sync(
                integration, days=days
            )
            pushed = push_channex_ari(integration)
        except (ChannexApiError, ChannexBookingIngestError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "availability_value_batches": len(availability_values),
                "restrictions_value_batches": len(restriction_values),
                "push_results": pushed,
            },
            status=status.HTTP_200_OK,
        )


class ChannexAriFlushView(TenantAPIView, APIView):
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]
    required_scopes = ["reception:write"]

    def post(self, request):
        integration = get_active_channex_integration(request.tenant.slug)
        try:
            pushed = push_channex_ari(integration)
        except ChannexApiError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        pending = ChannexAriOutbox.objects.filter(
            tenant=request.tenant,
            status=ChannexAriOutbox.Status.PENDING,
        ).count()
        return Response({"push_results": pushed, "pending_outbox": pending})
