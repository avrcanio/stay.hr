from datetime import date

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Prefetch

from apps.api.authentication import AppKeyAuthentication
from apps.api.permissions import DenyAdminScopes, HasApiApplication, HasReceptionAccess, HasScope
from apps.api.staff_authentication import StaffSessionAuthentication
from apps.api.serializers import (
    AppConfigSerializer,
    PublicPropertySerializer,
    PublicReservationCreateSerializer,
    PublicUnitSerializer,
)
from apps.integrations.models import UnitAvailabilityBlock
from apps.properties.models import Property, Unit, UnitBed, UnitBathroom
from apps.reservations.models import Reservation, ReservationUnit

BLOCKING_RESERVATION_STATUSES = frozenset(
    {
        Reservation.Status.PENDING,
        Reservation.Status.EXPECTED,
        Reservation.Status.CHECKED_IN,
    }
)


class TenantAPIView(APIView):
    authentication_classes = [AppKeyAuthentication, StaffSessionAuthentication]
    permission_classes = [HasApiApplication, DenyAdminScopes]


def _units_with_details_queryset(tenant):
    return (
        Unit.objects.for_tenant(tenant)
        .select_related("property")
        .prefetch_related(
            Prefetch(
                "beds",
                queryset=UnitBed.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "bathrooms",
                queryset=UnitBathroom.objects.order_by("sort_order", "id"),
            ),
        )
    )


class AppConfigView(TenantAPIView):
    required_scopes = ["public:read"]
    permission_classes = [HasReceptionAccess, DenyAdminScopes]

    def get(self, request):
        tenant = request.tenant
        properties = Property.objects.for_tenant(tenant).order_by("name")
        units = (
            _units_with_details_queryset(tenant)
            .filter(is_active=True)
            .order_by("property__name", "code")
        )
        primary = properties.filter(slug=tenant.slug).first() or properties.first()
        branding = {}
        if primary is not None:
            branding = primary.branding or {}

        payload = {
            "tenant": tenant,
            "properties": properties,
            "units": units,
            "feature_flags": {
                "public_booking": True,
                "availability_api": True,
            },
        }
        data = AppConfigSerializer(payload).data
        data["branding"] = branding
        return Response(data)


class PublicPropertiesView(TenantAPIView):
    required_scopes = ["public:read"]
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]

    def get(self, request):
        properties = Property.objects.for_tenant(request.tenant).order_by("name")
        serializer = PublicPropertySerializer(properties, many=True)
        return Response({"results": serializer.data})


class PublicUnitsView(TenantAPIView):
    required_scopes = ["public:read"]
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]

    def get(self, request):
        units = _units_with_details_queryset(request.tenant).filter(
            is_active=True,
        )
        property_slug = request.query_params.get("property")
        if property_slug:
            units = units.filter(property__slug=property_slug)
        units = units.order_by("property__name", "code")
        serializer = PublicUnitSerializer(units, many=True)
        return Response({"results": serializer.data})


class PublicAvailabilityView(TenantAPIView):
    required_scopes = ["public:read"]
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]

    def get(self, request):
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        property_slug = request.query_params.get("property")

        if not from_str or not to_str:
            return Response(
                {"detail": "Query params 'from' and 'to' (YYYY-MM-DD) are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from_date = date.fromisoformat(from_str)
            to_date = date.fromisoformat(to_str)
        except ValueError:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if to_date <= from_date:
            return Response(
                {"detail": "'to' must be after 'from'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.for_tenant(request.tenant).filter(
            is_active=True,
        ).select_related("property")
        if property_slug:
            units = units.filter(property__slug=property_slug)

        unit_list = list(units.order_by("property__name", "code"))
        unit_ids = [unit.id for unit in unit_list]
        blocked_by_unit: dict[int, list[dict]] = {uid: [] for uid in unit_ids}

        if unit_ids:
            reservation_units = (
                ReservationUnit.objects.filter(
                    tenant=request.tenant,
                    unit_id__in=unit_ids,
                    reservation__status__in=BLOCKING_RESERVATION_STATUSES,
                    reservation__check_in__lt=to_date,
                    reservation__check_out__gt=from_date,
                )
                .select_related("reservation")
            )
            for row in reservation_units:
                reservation = row.reservation
                blocked_by_unit[row.unit_id].append(
                    {
                        "booking_code": reservation.booking_code
                        or reservation.external_id
                        or "",
                        "check_in": reservation.check_in.isoformat(),
                        "check_out": reservation.check_out.isoformat(),
                        "status": reservation.status,
                    }
                )

            manual_blocks = UnitAvailabilityBlock.objects.filter(
                tenant=request.tenant,
                unit_id__in=unit_ids,
                check_in__lt=to_date,
                check_out__gt=from_date,
            )
            for block in manual_blocks:
                blocked_by_unit[block.unit_id].append(
                    {
                        "booking_code": block.smoobu_booking_id,
                        "check_in": block.check_in.isoformat(),
                        "check_out": block.check_out.isoformat(),
                        "status": "blocked",
                    }
                )

        results = []
        for unit in unit_list:
            results.append(
                {
                    "unit_id": unit.id,
                    "unit_code": unit.code,
                    "property_slug": unit.property.slug,
                    "blocked_periods": blocked_by_unit.get(unit.id, []),
                }
            )

        return Response(
            {
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "units": results,
            }
        )


class PublicReservationCreateView(TenantAPIView):
    required_scopes = ["reservations:create"]
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]

    def post(self, request):
        serializer = PublicReservationCreateSerializer(
            data=request.data,
            context={"tenant": request.tenant},
        )
        serializer.is_valid(raise_exception=True)
        reservation = serializer.save()
        return Response(
            {
                "id": reservation.id,
                "booking_code": reservation.booking_code,
                "status": reservation.status,
                "check_in": reservation.check_in.isoformat(),
                "check_out": reservation.check_out.isoformat(),
                "property_slug": reservation.property.slug,
            },
            status=status.HTTP_201_CREATED,
        )
