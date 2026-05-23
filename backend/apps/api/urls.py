from django.urls import include, path

from apps.api.views import (
    AppConfigView,
    PublicAvailabilityView,
    PublicPropertiesView,
    PublicReservationCreateView,
    PublicUnitsView,
)
from apps.api.site_context_views import SiteContextView
from apps.api.fcm_views import FcmTokenRegisterView

urlpatterns = [
    path("integrations/", include("apps.api.integrations_urls")),
    path("reception/", include("apps.api.reception_urls")),
    path("rooms/", include("apps.api.rooms_urls")),
    path("app/config", AppConfigView.as_view(), name="app-config"),
    path("app/fcm-token", FcmTokenRegisterView.as_view(), name="app-fcm-token"),
    path(
        "public/site-context/",
        SiteContextView.as_view(),
        name="public-site-context",
    ),
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
