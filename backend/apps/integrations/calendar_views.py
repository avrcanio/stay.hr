from __future__ import annotations

from datetime import date

from django.db.models import QuerySet
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import DenyAdminScopes, HasApiApplication, HasScope
from apps.api.views import TenantAPIView
from apps.integrations.models import UnitRateDay
from apps.integrations.smoobu.exceptions import (
    SmoobuApiError,
    SmoobuConfigError,
    SmoobuRatesError,
)
from apps.integrations.smoobu.rates_service import apply_rate_updates
from apps.integrations.smoobu.resolver import get_active_smoobu_integration


class CalendarRateUpdateItemSerializer(serializers.Serializer):
    unit_code = serializers.CharField()
    date = serializers.DateField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    rate = serializers.DecimalField(max_digits=10, decimal_places=2)
    min_stay = serializers.IntegerField(required=False, min_value=1)
    min_stay_arrival = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        has_single = bool(attrs.get("date"))
        has_range = bool(attrs.get("date_from")) and bool(attrs.get("date_to"))
        if has_single == has_range:
            raise serializers.ValidationError("Provide either date or date_from + date_to.")
        return attrs


class CalendarRateDaySerializer(serializers.Serializer):
    unit_code = serializers.CharField(source="unit.code")
    date = serializers.DateField()
    rate = serializers.DecimalField(max_digits=10, decimal_places=2)
    min_stay = serializers.IntegerField(allow_null=True)
    smoobu_synced_at = serializers.DateTimeField(allow_null=True)


def _parse_query_date(value: str | None, *, name: str) -> date:
    if not value:
        raise serializers.ValidationError({name: "This query parameter is required."})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise serializers.ValidationError({name: "Invalid date (use YYYY-MM-DD)."}) from exc


def _should_push(request, *, default: bool = True) -> bool:
    raw = request.query_params.get("push")
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _rate_days_queryset(
    request,
    *,
    date_from: date,
    date_to: date,
    unit_code: str | None,
) -> QuerySet[UnitRateDay]:
    if date_to < date_from:
        raise serializers.ValidationError({"to": "Must be on or after from."})

    qs = (
        UnitRateDay.objects.filter(
            tenant=request.tenant,
            date__gte=date_from,
            date__lte=date_to,
        )
        .select_related("unit")
        .order_by("unit__code", "date")
    )
    if unit_code:
        qs = qs.filter(unit__code=unit_code)
    return qs


class CalendarRatesView(TenantAPIView, APIView):
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]
    required_scopes = ["reception:write"]

    def get(self, request):
        date_from = _parse_query_date(request.query_params.get("from"), name="from")
        date_to = _parse_query_date(request.query_params.get("to"), name="to")
        unit_code = (request.query_params.get("unit_code") or "").strip() or None

        rows = _rate_days_queryset(
            request,
            date_from=date_from,
            date_to=date_to,
            unit_code=unit_code,
        )
        serializer = CalendarRateDaySerializer(rows, many=True)
        return Response(
            {
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
                "unit_code": unit_code,
                "rates": serializer.data,
            }
        )

    def patch(self, request):
        serializer = CalendarRateUpdateItemSerializer(
            data=request.data.get("updates", []),
            many=True,
        )
        serializer.is_valid(raise_exception=True)

        try:
            integration = get_active_smoobu_integration(request.tenant.slug)
            rows, push_results = apply_rate_updates(
                integration,
                serializer.validated_data,
                push=_should_push(request),
            )
        except SmoobuConfigError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (SmoobuApiError, SmoobuRatesError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        unsynced = UnitRateDay.objects.filter(
            tenant=request.tenant,
            id__in=[row.id for row in rows],
            smoobu_synced_at__isnull=True,
        ).count()

        return Response(
            {
                "updated_days": len(rows),
                "push_results": push_results,
                "unsynced_days": unsynced,
            },
            status=status.HTTP_200_OK,
        )
