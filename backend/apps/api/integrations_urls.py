from django.urls import path

from apps.integrations.calendar_views import CalendarRatesView
from apps.integrations.channex.ari_views import (
    ChannexAriAvailabilityView,
    ChannexAriFlushView,
    ChannexAriFullSyncView,
    ChannexAriRatesView,
)
from apps.integrations.channex.webhook_views import ChannexWebhookView
from apps.integrations.smoobu.webhook_views import SmoobuWebhookView
from apps.integrations.whatsapp.webhook_views import WhatsAppWebhookView

urlpatterns = [
    path(
        "calendar/rates/",
        CalendarRatesView.as_view(),
        name="calendar-rates",
    ),
    path(
        "channex/webhook/",
        ChannexWebhookView.as_view(),
        name="channex-webhook",
    ),
    path(
        "smoobu/webhook/",
        SmoobuWebhookView.as_view(),
        name="smoobu-webhook",
    ),
    path(
        "whatsapp/webhook/",
        WhatsAppWebhookView.as_view(),
        name="whatsapp-webhook",
    ),
    path(
        "channex/ari/rates/",
        ChannexAriRatesView.as_view(),
        name="channex-ari-rates",
    ),
    path(
        "channex/ari/availability/",
        ChannexAriAvailabilityView.as_view(),
        name="channex-ari-availability",
    ),
    path(
        "channex/ari/full-sync/",
        ChannexAriFullSyncView.as_view(),
        name="channex-ari-full-sync",
    ),
    path(
        "channex/ari/flush/",
        ChannexAriFlushView.as_view(),
        name="channex-ari-flush",
    ),
]
