from django.urls import include, path

from apps.api.views import (
    AppConfigView,
    PublicAvailabilityView,
    PublicPropertiesView,
    PublicReservationCreateView,
    PublicUnitsView,
)

urlpatterns = [
    path("reception/", include("apps.api.reception_urls")),
    path("rooms/", include("apps.api.rooms_urls")),
    path("app/config", AppConfigView.as_view(), name="app-config"),
    path("public/properties", PublicPropertiesView.as_view(), name="public-properties"),
    path("public/units", PublicUnitsView.as_view(), name="public-units"),
    path(
        "public/availability",
        PublicAvailabilityView.as_view(),
        name="public-availability",
    ),
    path(
        "public/reservations",
        PublicReservationCreateView.as_view(),
        name="public-reservations",
    ),
]
