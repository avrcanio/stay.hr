from django.urls import path

from apps.api.platform_whatsapp_views import PlatformWhatsAppUnroutedView

urlpatterns = [
    path(
        "whatsapp/unrouted/",
        PlatformWhatsAppUnroutedView.as_view(),
        name="platform-whatsapp-unrouted",
    ),
    path(
        "whatsapp/unrouted/<int:routing_id>/",
        PlatformWhatsAppUnroutedView.as_view(),
        name="platform-whatsapp-unrouted-action",
    ),
]
