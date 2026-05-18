from django.contrib import admin

from apps.reservations.models import EvisitorSubmission, Guest, Reservation, ReservationUnit


class GuestInline(admin.TabularInline):
    model = Guest
    extra = 0
    fields = ("first_name", "last_name", "is_primary", "evisitor_status", "email")


class ReservationUnitInline(admin.TabularInline):
    model = ReservationUnit
    extra = 0


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "booking_code",
        "property",
        "tenant",
        "check_in",
        "check_out",
        "status",
        "booker_name",
    )
    list_filter = ("tenant", "status", "property")
    search_fields = (
        "booking_code",
        "external_id",
        "booker_name",
        "booker_email",
    )
    raw_id_fields = ("tenant", "property")
    date_hierarchy = "check_in"
    inlines = [ReservationUnitInline, GuestInline]


@admin.register(ReservationUnit)
class ReservationUnitAdmin(admin.ModelAdmin):
    list_display = ("reservation", "room_name", "unit", "sort_order", "tenant")
    list_filter = ("tenant",)
    raw_id_fields = ("tenant", "reservation", "unit")


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("name", "reservation", "tenant", "is_primary", "evisitor_status", "email")
    list_filter = ("tenant",)
    search_fields = ("name", "email", "reservation__booking_code")
    raw_id_fields = ("tenant", "reservation")


@admin.register(EvisitorSubmission)
class EvisitorSubmissionAdmin(admin.ModelAdmin):
    list_display = ("guest", "status", "registration_id", "submitted_at", "tenant")
    list_filter = ("status", "tenant")
    raw_id_fields = ("tenant", "guest")
