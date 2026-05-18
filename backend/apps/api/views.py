from datetime import date

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.authentication import AppKeyAuthentication
from apps.api.permissions import DenyAdminScopes, HasApiApplication, HasScope
from apps.api.serializers import (
    AppConfigSerializer,
    PublicPropertySerializer,
    PublicReservationCreateSerializer,
    PublicUnitSerializer,
)
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation


class TenantAPIView(APIView):
    authentication_classes = [AppKeyAuthentication]
    permission_classes = [HasApiApplication, DenyAdminScopes]


class AppConfigView(TenantAPIView):
    required_scopes = ["public:read"]
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]

    def get(self, request):
        tenant = request.tenant
        properties = Property.objects.filter(tenant=tenant).order_by("name")
        units = (
            Unit.objects.filter(tenant=tenant, is_active=True)
            .select_related("property")
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
        properties = Property.objects.filter(tenant=request.tenant).order_by("name")
        serializer = PublicPropertySerializer(properties, many=True)
        return Response({"results": serializer.data})


class PublicUnitsView(TenantAPIView):
    required_scopes = ["public:read"]
    permission_classes = [HasApiApplication, HasScope, DenyAdminScopes]

    def get(self, request):
        units = Unit.objects.filter(
            tenant=request.tenant,
            is_active=True,
        ).select_related("property")
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

        units = Unit.objects.filter(
            tenant=request.tenant,
            is_active=True,
        ).select_related("property")
        if property_slug:
            units = units.filter(property__slug=property_slug)

        reservations = Reservation.objects.filter(
            tenant=request.tenant,
            status__in=[Reservation.Status.PENDING, Reservation.Status.CONFIRMED],
            check_in__lt=to_date,
            check_out__gt=from_date,
        )
        if property_slug:
            reservations = reservations.filter(property__slug=property_slug)

        blocked_by_property: dict[str, list[dict]] = {}
        for reservation in reservations.select_related("property"):
            key = reservation.property.slug
            blocked_by_property.setdefault(key, []).append(
                {
                    "booking_code": reservation.booking_code,
                    "check_in": reservation.check_in.isoformat(),
                    "check_out": reservation.check_out.isoformat(),
                    "status": reservation.status,
                }
            )

        results = []
        for unit in units.order_by("property__name", "code"):
            results.append(
                {
                    "unit_id": unit.id,
                    "unit_code": unit.code,
                    "property_slug": unit.property.slug,
                    "blocked_periods": blocked_by_property.get(unit.property.slug, []),
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
