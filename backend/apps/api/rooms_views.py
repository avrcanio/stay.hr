from __future__ import annotations

from django.db.models import Prefetch
from django.utils.dateparse import parse_date
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound

from apps.api.reception_views import ReceptionReadView
from apps.properties.models import Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.reservations.reservation_units import joined_room_names


def _pick_lang(request) -> str:
    raw = (request.query_params.get("lang") or "").strip()
    if raw:
        return raw
    header = (request.headers.get("Accept-Language") or "").strip()
    if not header:
        return "en"
    return header.split(",")[0].strip() or "en"


class UnitListSerializer(serializers.ModelSerializer):
    room_type = serializers.SerializerMethodField()
    room_type_name = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = ("id", "code", "room_type", "room_type_name", "is_active")

    def get_room_type(self, obj):
        return None

    def get_room_type_name(self, obj):
        return obj.name or ""


class UnitCalendarReservationSerializer(serializers.ModelSerializer):
    check_in_date = serializers.DateField(source="check_in", read_only=True)
    check_out_date = serializers.DateField(source="check_out", read_only=True)
    primary_guest_name = serializers.SerializerMethodField()
    primary_guest_nationality_iso2 = serializers.SerializerMethodField()
    room_name = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = (
            "id",
            "external_id",
            "check_in_date",
            "check_out_date",
            "status",
            "room_name",
            "primary_guest_name",
            "primary_guest_nationality_iso2",
        )

    def get_room_name(self, obj) -> str:
        return joined_room_names(obj)

    def get_primary_guest_name(self, obj):
        primary = next((g for g in obj.guests.all() if g.is_primary), None)
        if not primary:
            return ""
        return f"{primary.first_name} {primary.last_name}".strip()

    def get_primary_guest_nationality_iso2(self, obj):
        primary = next((g for g in obj.guests.all() if g.is_primary), None)
        if not primary:
            return ""
        return (primary.nationality or "").strip().upper()


class UnitListView(ReceptionReadView, generics.ListAPIView):
    serializer_class = UnitListSerializer

    def get_queryset(self):
        return Unit.objects.for_tenant(self.request.tenant).filter(
            is_active=True,
        ).order_by("code")


class UnitCalendarView(ReceptionReadView, generics.ListAPIView):
    serializer_class = UnitCalendarReservationSerializer

    def _include_canceled(self) -> bool:
        raw = (self.request.query_params.get("include_canceled") or "").strip().lower()
        return raw in ("1", "true", "yes")

    def get_queryset(self):
        tenant = self.request.tenant
        room_id = self.kwargs["room_id"]
        if not Unit.objects.for_tenant(tenant).filter(pk=room_id).exists():
            raise NotFound("Soba nije pronađena.")

        qs = (
            Reservation.objects.for_tenant(tenant)
            .filter(units__unit_id=room_id)
            .distinct()
            .prefetch_related(
                "guests",
                Prefetch(
                    "units",
                    queryset=ReservationUnit.objects.select_related("unit").order_by(
                        "sort_order", "id"
                    ),
                ),
            )
            .order_by("check_in", "id")
        )
        if not self._include_canceled():
            qs = qs.exclude(status=Reservation.Status.CANCELED)

        from_raw = (self.request.query_params.get("from") or "").strip()
        to_raw = (self.request.query_params.get("to") or "").strip()
        date_from = parse_date(from_raw) if from_raw else None
        date_to = parse_date(to_raw) if to_raw else None
        if date_from:
            qs = qs.filter(check_out__gt=date_from)
        if date_to:
            qs = qs.filter(check_in__lt=date_to)
        return qs
