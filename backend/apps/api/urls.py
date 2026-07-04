from django.urls import include, path

from apps.api.auth_views import (
    ReceptionLoginView,
    ReceptionLogoutView,
    ReceptionSessionView,
)
from apps.api.billing_views import PublicInvoiceHtmlView, PublicInvoicePdfView
from apps.api.views import (
    AppConfigView,
    PublicAvailabilityView,
    PublicPropertiesView,
    PublicReservationCreateView,
    PublicReservationStatusView,
    PublicUnitsView,
)
from apps.api.site_context_views import SiteContextView
from apps.api.fcm_views import FcmTokenRegisterView

urlpatterns = [
    path("auth/reception-login/", ReceptionLoginView.as_view(), name="reception-login"),
    path("auth/reception-logout/", ReceptionLogoutView.as_view(), name="reception-logout"),
    path("auth/reception-session/", ReceptionSessionView.as_view(), name="reception-session"),
    path("integrations/", include("apps.api.integrations_urls")),
    path("platform/", include("apps.api.platform_urls")),
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
    path(
        "public/invoices/<uuid:public_access_token>/",
        PublicInvoiceHtmlView.as_view(),
        name="public-invoice-html",
    ),
    path(
        "public/invoices/<uuid:public_access_token>/pdf/",
        PublicInvoicePdfView.as_view(),
        name="public-invoice-pdf",
    ),
    path(
        "public/reservations/<str:booking_code>",
        PublicReservationStatusView.as_view(),
        name="public-reservation-status",
    ),
]
