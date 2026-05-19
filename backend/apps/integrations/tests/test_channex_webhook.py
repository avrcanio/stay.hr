import os

from django.test import RequestFactory, TestCase, override_settings

from apps.integrations.channex.webhook_auth import (
    EXPECTED_ENV,
    EXPECTED_PROVIDER,
    WEBHOOK_HEADER_NAME,
    verify_channex_webhook_request,
)
from apps.integrations.channex.webhook_views import ChannexWebhookView


@override_settings(ROOT_URLCONF="config.urls")
class ChannexWebhookViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
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
