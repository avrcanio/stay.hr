from django.urls import path

from apps.integrations.channex.ari_views import (
    ChannexAriAvailabilityView,
    ChannexAriFlushView,
    ChannexAriFullSyncView,
    ChannexAriRatesView,
)
from apps.integrations.channex.webhook_views import ChannexWebhookView

urlpatterns = [
    path(
        "channex/webhook/",
        ChannexWebhookView.as_view(),
        name="channex-webhook",
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
