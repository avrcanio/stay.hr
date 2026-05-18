from django.contrib import admin

from apps.reservations.models import Guest, Reservation


class GuestInline(admin.TabularInline):
    model = Guest
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
    inlines = [GuestInline]


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("name", "reservation", "tenant", "email", "phone")
    list_filter = ("tenant",)
    search_fields = ("name", "email", "reservation__booking_code")
    raw_id_fields = ("tenant", "reservation")
