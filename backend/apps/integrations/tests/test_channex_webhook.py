import os

from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.integrations.channex.booking_service import channex_external_id
from apps.integrations.channex.webhook_auth import (
    EXPECTED_ENV,
    EXPECTED_PROVIDER,
    WEBHOOK_HEADER_NAME,
    verify_channex_webhook_request,
)
from apps.integrations.channex.webhook_views import ChannexWebhookView
from apps.integrations.models import ChannexMessage, IntegrationConfig
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


@override_settings(ROOT_URLCONF="config.urls")
class ChannexWebhookViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.api_factory = APIRequestFactory()
        os.environ["CHANNEX_WEBHOOK_SECRET"] = "test-webhook-secret-value"

    def tearDown(self):
        os.environ.pop("CHANNEX_WEBHOOK_SECRET", None)

    def _url(self):
        return f"/api/v1/integrations/channex/webhook/?provider={EXPECTED_PROVIDER}&env={EXPECTED_ENV}"

    def test_rejects_missing_header(self):
        request = self.factory.post(
            self._url(),
            data={"event": "booking_new", "property_id": "x"},
            content_type="application/json",
        )
        response = ChannexWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 401)

    def test_accepts_valid_webhook(self):
        request = self.factory.post(
            self._url(),
            {
                "event": "ping",
                "property_id": "e00e6034-c154-4754-b5d9-9fff73ad12f6",
            },
            format="json",
            HTTP_X_STAY_CHANNEX_WEBHOOK="test-webhook-secret-value",
        )
        response = ChannexWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")

    def test_verify_helper(self):
        request = self.factory.get(
            self._url(),
            HTTP_X_STAY_CHANNEX_WEBHOOK="test-webhook-secret-value",
        )
        self.assertTrue(
            verify_channex_webhook_request(request, config_secret="test-webhook-secret-value")
        )

    def test_message_webhook_via_http(self):
        tenant = Tenant.objects.create(slug="webhook-msg", name="Webhook Msg")
        prop = Property.objects.create(
            tenant=tenant,
            slug="webhook-msg",
            name="Webhook Msg",
            timezone="Europe/Zagreb",
        )
        integration = IntegrationConfig.objects.create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        property_id = "prop-msg-webhook-001"
        secret = "test-webhook-secret-value"
        integration.set_config_dict(
            {
                "property_id": property_id,
                "webhook_secret": secret,
                "sync_property_slug": "webhook-msg",
            }
        )
        integration.save()
        booking_id = "booking-msg-001"
        reservation = Reservation.objects.create(
            tenant=tenant,
            property=prop,
            external_id=channex_external_id(booking_id),
            import_source="channex",
            check_in="2026-06-20",
            check_out="2026-06-21",
            booker_name="Guest",
            status=Reservation.Status.EXPECTED,
        )

        request = self.api_factory.post(
            self._url(),
            {
                "event": "message",
                "property_id": property_id,
                "payload": {
                    "id": "msg-http-1",
                    "message": "Inbound via HTTP webhook",
                    "sender": "guest",
                    "booking_id": booking_id,
                },
            },
            format="json",
            HTTP_X_STAY_CHANNEX_WEBHOOK=secret,
        )
        response = ChannexWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["event"], "message")

        row = ChannexMessage.objects.get(channex_message_id="msg-http-1")
        self.assertEqual(row.reservation_id, reservation.id)
        self.assertEqual(row.body, "Inbound via HTTP webhook")
