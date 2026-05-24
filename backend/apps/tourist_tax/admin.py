from django.contrib import admin

from apps.tourist_tax.models import (
    TouristTaxAccommodationCategory,
    TouristTaxAgeBracket,
    TouristTaxOrdinance,
    TouristTaxRate,
    TouristTaxSeason,
    TouristTaxZone,
)


class TouristTaxRateInline(admin.TabularInline):
    model = TouristTaxRate
    extra = 0
    fields = ("season", "category", "amount")
    autocomplete_fields = ("season", "category")
    ordering = ("season__code", "category__code")


class TouristTaxSeasonInline(admin.TabularInline):
    model = TouristTaxSeason
    extra = 0
    fields = ("code", "kind", "start_month", "start_day", "end_month", "end_day")
    ordering = ("code",)


class TouristTaxAgeBracketInline(admin.TabularInline):
    model = TouristTaxAgeBracket
    extra = 0
    fields = ("code", "min_age", "max_age", "multiplier", "sort_order")
    ordering = ("sort_order",)


@admin.register(TouristTaxOrdinance)
class TouristTaxOrdinanceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "issuer", "valid_from", "valid_to", "currency", "is_active")
    list_filter = ("is_active", "currency")
    search_fields = ("code", "name", "issuer")
    readonly_fields = ("created_at", "updated_at")
    inlines = [TouristTaxSeasonInline, TouristTaxAgeBracketInline]


@admin.register(TouristTaxZone)
class TouristTaxZoneAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "ordinance")
    list_filter = ("kind", "ordinance")
    search_fields = ("code", "name")
    readonly_fields = ("created_at", "updated_at")
    inlines = [TouristTaxRateInline]


@admin.register(TouristTaxSeason)
class TouristTaxSeasonAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "kind",
        "ordinance",
        "start_month",
        "start_day",
        "end_month",
        "end_day",
    )
    list_filter = ("kind", "ordinance")
    search_fields = ("code",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(TouristTaxAccommodationCategory)
class TouristTaxAccommodationCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TouristTaxRate)
class TouristTaxRateAdmin(admin.ModelAdmin):
    list_display = ("zone", "season", "category", "amount")
    list_filter = ("zone__ordinance", "zone", "season", "category")
    search_fields = ("zone__code", "season__code", "category__code")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("zone", "season", "category")


@admin.register(TouristTaxAgeBracket)
class TouristTaxAgeBracketAdmin(admin.ModelAdmin):
    list_display = ("code", "ordinance", "min_age", "max_age", "multiplier", "sort_order")
    list_filter = ("ordinance",)
    search_fields = ("code",)
    readonly_fields = ("created_at", "updated_at")
