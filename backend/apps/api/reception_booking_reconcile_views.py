"""Reception API for Booking.com XLS reconcile."""

from __future__ import annotations

from django.utils.dateparse import parse_date
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.reception_booking_reconcile_serializers import (
    booking_reconcile_apply_results_to_dict,
    booking_reconcile_result_to_dict,
    parse_apply_field_keys,
)
from apps.api.reception_views import ReceptionReadView, ReceptionWriteView
from apps.properties.resolution import PropertyResolutionError, resolve_property_for_tenant
from apps.reservations.booking_xls_import import validate_booking_export_file
from apps.reservations.reports.booking_reconcile import (
    compare_booking_export,
    recompare_from_snapshot,
)
from apps.reservations.reports.booking_reconcile_apply import (
    BookingReconcileApplyItem,
    apply_booking_reconcile_fixes,
)
from apps.reservations.reports.booking_reconcile_types import BookingReconcileParams

MAX_BOOKING_XLS_BYTES = 5 * 1024 * 1024


class BookingReconcileCompareSerializer(serializers.Serializer):
    file = serializers.FileField()
    property_slug = serializers.CharField()
    date_axis = serializers.ChoiceField(
        choices=["check_out", "check_in"],
        required=False,
        allow_null=True,
    )
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)

    def validate_file(self, value):
        if value.size > MAX_BOOKING_XLS_BYTES:
            raise serializers.ValidationError(
                f"Datoteka je prevelika (max {MAX_BOOKING_XLS_BYTES} bajtova)."
            )
        return value


class BookingReconcileApplyItemSerializer(serializers.Serializer):
    booking_code = serializers.CharField()
    fields = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    mode = serializers.ChoiceField(
        choices=["fill_empty", "overwrite"],
        required=False,
        allow_null=True,
    )


class BookingReconcileApplySerializer(serializers.Serializer):
    snapshot_id = serializers.UUIDField()
    property_slug = serializers.CharField()
    mode = serializers.ChoiceField(choices=["fill_empty", "overwrite"], default="fill_empty")
    confirm_overwrite = serializers.BooleanField(default=False)
    items = BookingReconcileApplyItemSerializer(many=True)


class BookingReconcileRecompareSerializer(serializers.Serializer):
    snapshot_id = serializers.UUIDField()
    property_slug = serializers.CharField()


class BookingReconcileCompareView(ReceptionReadView, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = BookingReconcileCompareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        upload = data["file"]
        content = upload.read()
        try:
            validate_booking_export_file(filename=upload.name, content=content)
        except ValueError as exc:
            return Response({"code": "invalid_file", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            prop = resolve_property_for_tenant(
                request.tenant,
                slug=data["property_slug"],
            )
        except PropertyResolutionError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        params = BookingReconcileParams(
            tenant=request.tenant,
            property=prop,
            date_axis=data.get("date_axis"),
            date_from=data.get("date_from"),
            date_to_inclusive=data.get("date_to"),
            filename=upload.name,
        )
        result = compare_booking_export(params=params, content=content, store_snapshot=True)
        return Response(booking_reconcile_result_to_dict(result))


class BookingReconcileRecompareView(ReceptionReadView, APIView):
    def post(self, request):
        serializer = BookingReconcileRecompareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            prop = resolve_property_for_tenant(request.tenant, slug=data["property_slug"])
        except PropertyResolutionError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        snapshot_id = str(data["snapshot_id"])
        try:
            result = recompare_from_snapshot(snapshot_id=snapshot_id, store_snapshot=True)
        except ValueError as exc:
            if str(exc) == "snapshot_not_found":
                return Response(
                    {"code": "snapshot_not_found", "detail": str(exc)},
                    status=status.HTTP_404_NOT_FOUND,
                )
            raise

        if result.meta.tenant_id != request.tenant.id or result.meta.property_id != prop.id:
            return Response(
                {"code": "snapshot_scope_mismatch", "detail": "Snapshot scope mismatch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(booking_reconcile_result_to_dict(result))


class BookingReconcileApplyView(ReceptionWriteView, APIView):
    def post(self, request):
        serializer = BookingReconcileApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        property_slug = data["property_slug"]

        try:
            prop = resolve_property_for_tenant(request.tenant, slug=property_slug)
        except PropertyResolutionError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        items = []
        for raw_item in data["items"]:
            try:
                fields = parse_apply_field_keys(raw_item.get("fields") or [])
            except ValueError as exc:
                return Response({"code": "invalid_field", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            items.append(
                BookingReconcileApplyItem(
                    booking_code=raw_item["booking_code"],
                    fields=fields,
                    mode=raw_item.get("mode"),
                )
            )

        results = apply_booking_reconcile_fixes(
            tenant=request.tenant,
            property=prop,
            snapshot_id=str(data["snapshot_id"]),
            items=tuple(items),
            default_mode=data["mode"],
            confirm_overwrite=data["confirm_overwrite"],
            applied_by=_booking_reconcile_actor(request),
        )
        return Response(booking_reconcile_apply_results_to_dict(results))


def _booking_reconcile_actor(request) -> str:
    app = getattr(request, "api_application", None)
    if app is not None:
        return f"api_app:{app.name}"
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.username}"
    return ""
