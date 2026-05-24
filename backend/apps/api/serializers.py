import secrets

from rest_framework import serializers

from apps.properties.models import Property, Unit, UnitBed, UnitBathroom
from apps.reservations.availability import validate_unit_available_for_booking
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant


class TenantSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = (
            "id",
            "name",
            "slug",
            "status",
            "timezone",
            "default_language",
        )


class PropertySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = (
            "id",
            "name",
            "slug",
            "address",
            "contact",
            "branding",
            "timezone",
            "language",
        )


class UnitBathroomSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitBathroom
        fields = (
            "is_private",
            "is_inside_room",
            "sort_order",
        )


class UnitBedSerializer(serializers.ModelSerializer):
    bed_type_label = serializers.CharField(source="get_bed_type_display", read_only=True)

    class Meta:
        model = UnitBed
        fields = (
            "bed_type",
            "bed_type_label",
            "count",
            "sort_order",
        )


class UnitSummarySerializer(serializers.ModelSerializer):
    property_slug = serializers.CharField(source="property.slug", read_only=True)
    beds = UnitBedSerializer(many=True, read_only=True)
    bathrooms = UnitBathroomSerializer(many=True, read_only=True)

    class Meta:
        model = Unit
        fields = (
            "id",
            "property_slug",
            "code",
            "name",
            "capacity_max_guests",
            "capacity_adults",
            "capacity_children",
            "capacity_infants",
            "beds",
            "bathrooms",
            "is_active",
        )


class AppConfigSerializer(serializers.Serializer):
    tenant = TenantSummarySerializer()
    properties = PropertySummarySerializer(many=True)
    units = UnitSummarySerializer(many=True)
    channel_manager = serializers.CharField()
    feature_flags = serializers.DictField()


class PublicPropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = (
            "id",
            "name",
            "slug",
            "address",
            "contact",
            "branding",
            "timezone",
            "language",
        )


class PublicUnitSerializer(serializers.ModelSerializer):
    property_slug = serializers.CharField(source="property.slug", read_only=True)
    beds = UnitBedSerializer(many=True, read_only=True)
    bathrooms = UnitBathroomSerializer(many=True, read_only=True)

    class Meta:
        model = Unit
        fields = (
            "id",
            "property_slug",
            "code",
            "name",
            "capacity_max_guests",
            "capacity_adults",
            "capacity_children",
            "capacity_infants",
            "beds",
            "bathrooms",
        )


class GuestInputSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=120)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)


class PublicReservationStatusSerializer(serializers.Serializer):
    booking_code = serializers.CharField()
    status = serializers.CharField()
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    property_slug = serializers.CharField()
    unit_code = serializers.CharField()
    booker_name = serializers.CharField()


class PublicReservationCreateSerializer(serializers.Serializer):
    property_slug = serializers.SlugField()
    unit_id = serializers.IntegerField()
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    booker_name = serializers.CharField(max_length=255)
    booker_email = serializers.EmailField(required=False, allow_blank=True)
    booker_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    total_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    currency = serializers.CharField(max_length=3, default="EUR", required=False)
    source = serializers.CharField(max_length=64, required=False, allow_blank=True)
    guests = GuestInputSerializer(many=True, required=False)

    def validate(self, attrs):
        if attrs["check_out"] <= attrs["check_in"]:
            raise serializers.ValidationError(
                {"check_out": "Check-out must be after check-in."}
            )

        tenant = self.context["tenant"]
        property_slug = attrs["property_slug"]
        unit_id = attrs["unit_id"]

        try:
            prop = Property.objects.get(tenant=tenant, slug=property_slug)
        except Property.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"property_slug": "Property not found."}
            ) from exc

        unit = (
            Unit.objects.for_tenant(tenant)
            .filter(pk=unit_id, property=prop, is_active=True)
            .first()
        )
        if unit is None:
            raise serializers.ValidationError({"unit_id": "Unit not found for this property."})

        try:
            validate_unit_available_for_booking(
                tenant,
                unit,
                attrs["check_in"],
                attrs["check_out"],
            )
        except ValueError as exc:
            raise serializers.ValidationError({"unit_id": str(exc)}) from exc

        attrs["property"] = prop
        attrs["unit"] = unit
        return attrs

    def create(self, validated_data):
        tenant = self.context["tenant"]
        prop = validated_data.pop("property")
        unit = validated_data.pop("unit")
        validated_data.pop("property_slug")
        validated_data.pop("unit_id")
        guests_data = validated_data.pop("guests", [])
        total_amount = validated_data.pop("total_amount", None)

        booking_code = self._generate_booking_code(tenant)
        reservation = Reservation.objects.create(
            tenant=tenant,
            property=prop,
            booking_code=booking_code,
            check_in=validated_data["check_in"],
            check_out=validated_data["check_out"],
            booker_name=validated_data["booker_name"],
            booker_email=validated_data.get("booker_email", ""),
            booker_phone=validated_data.get("booker_phone", ""),
            amount=total_amount,
            currency=validated_data.get("currency", "EUR"),
            source=validated_data.get("source", "api"),
            status=Reservation.Status.PENDING,
        )

        ReservationUnit.objects.create(
            tenant=tenant,
            reservation=reservation,
            unit=unit,
            sort_order=0,
            room_name=unit.name or unit.code,
            amount=total_amount,
        )

        for guest_data in guests_data:
            last = guest_data.get("last_name", "").strip()
            first = guest_data["first_name"].strip()
            name = f"{first} {last}".strip() if last else first
            Guest.objects.create(
                tenant=tenant,
                reservation=reservation,
                name=name,
                email=guest_data.get("email", ""),
                phone=guest_data.get("phone", ""),
            )

        return reservation

    def _generate_booking_code(self, tenant: Tenant) -> str:
        for _ in range(10):
            code = secrets.token_hex(4).upper()
            if not Reservation.objects.filter(tenant=tenant, booking_code=code).exists():
                return code
        return secrets.token_hex(6).upper()
