import hashlib
import hmac
import json
import os
from datetime import date, timedelta
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.reply import build_greeting
from apps.integrations.whatsapp.reservation_lookup import find_reservation_for_wa_id
from apps.integrations.whatsapp.resolver import find_whatsapp_integration
from apps.integrations.whatsapp.webhook_auth import verify_webhook_signature, verify_webhook_subscription
from apps.integrations.whatsapp.webhook_views import WhatsAppWebhookView
from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="
TEST_VERIFY_TOKEN = "stay-whatsapp-verify-token"
TEST_APP_SECRET = "whatsapp-test-app-secret"


def _signed_post(factory: RequestFactory, url: str, payload: dict):
    raw = json.dumps(payload).encode("utf-8")
    signature = (
        "sha256="
        + hmac.new(TEST_APP_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    )
    return factory.post(
        url,
        data=raw,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )


def _sample_webhook_payload(*, phone_number_id: str, wa_id: str, wamid: str, body: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+385911111111",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Ana Anić"},
                                    "wa_id": wa_id,
                                }
                            ],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": wamid,
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@override_settings(
    ROOT_URLCONF="config.urls",
    STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class WhatsAppWebhookTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = TEST_VERIFY_TOKEN
        os.environ["WHATSAPP_APP_SECRET"] = TEST_APP_SECRET

        self.tenant_a = Tenant.objects.create(
            slug="uzorita",
            name="Uzorita",
            default_language="hr",
        )
        self.tenant_b = Tenant.objects.create(
            slug="other-hotel",
            name="Other Hotel",
            default_language="en",
        )
        self.property_a = Property.objects.create(
            tenant=self.tenant_a,
            slug="uzorita",
            name="Uzorita Apartments",
            language="hr",
        )
        self.property_b = Property.objects.create(
            tenant=self.tenant_b,
            slug="other",
            name="Other Property",
            language="en",
        )

        self.phone_number_id_a = "7794189252778687"
        self.phone_number_id_b = "9988776655443322"

        self.integration_a = IntegrationConfig.objects.create(
            tenant=self.tenant_a,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key=self.phone_number_id_a,
            is_active=True,
        )
        self.integration_a.set_config_dict(
            {
                "phone_number_id": self.phone_number_id_a,
                "display_phone_number": "+385911111111",
                "waba_id": "215589313241560883",
                "access_token": "tenant-a-token",
                "auto_reply": True,
            }
        )
        self.integration_a.save()

        self.integration_b = IntegrationConfig.objects.create(
            tenant=self.tenant_b,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key=self.phone_number_id_b,
            is_active=True,
        )
        self.integration_b.set_config_dict(
            {
                "phone_number_id": self.phone_number_id_b,
                "display_phone_number": "+385922222222",
                "waba_id": "999999999999999",
                "access_token": "tenant-b-token",
                "auto_reply": True,
            }
        )
        self.integration_b.save()

        today = timezone.localdate()
        self.reservation_a = Reservation.objects.create(
            tenant=self.tenant_a,
            property=self.property_a,
            booking_code="BCOM-9001",
            booker_name="Ana Anić",
            booker_phone="+385 91 111 1111",
            check_in=today + timedelta(days=2),
            check_out=today + timedelta(days=5),
            status=Reservation.Status.EXPECTED,
        )
        Guest.objects.create(
            tenant=self.tenant_a,
            reservation=self.reservation_a,
            first_name="Ana",
            last_name="Anić",
            name="Ana Anić",
            phone="+385911111111",
            is_primary=True,
        )

    def tearDown(self):
        os.environ.pop("WHATSAPP_WEBHOOK_VERIFY_TOKEN", None)
        os.environ.pop("WHATSAPP_APP_SECRET", None)

    def _url(self):
        return "/api/v1/integrations/whatsapp/webhook/"

    def test_verify_handshake(self):
        request = self.factory.get(
            self._url(),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": TEST_VERIFY_TOKEN,
                "hub.challenge": "1234567890",
            },
        )
        response = WhatsAppWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), "1234567890")

    def test_verify_handshake_rejects_bad_token(self):
        request = self.factory.get(
            self._url(),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "1234567890",
            },
        )
        response = WhatsAppWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_verify_handshake_rejects_non_ascii_token_without_500(self):
        request = self.factory.get(
            self._url(),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "VAŠ_TOKEN",
                "hub.challenge": "1234567890",
            },
        )
        response = WhatsAppWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    @patch.dict("os.environ", {"WHATSAPP_WEBHOOK_VERIFY_SIGNATURE": "false"}, clear=False)
    def test_post_accepts_unsigned_payload_when_signature_disabled(self):
        payload = _sample_webhook_payload(
            phone_number_id=self.phone_number_id_a,
            wa_id="385911111111",
            wamid="wamid.inbound.unsigned",
            body="Bok",
        )
        request = self.factory.post(
            self._url(),
            data=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        with patch("apps.integrations.whatsapp.tasks.send_text_message") as mock_send:
            mock_send.return_value = {"messages": [{"id": "wamid.outbound.unsigned"}]}
            response = WhatsAppWebhookView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            WhatsAppMessage.objects.filter(wamid="wamid.inbound.unsigned").exists()
        )

    def test_routes_by_phone_number_id(self):
        payload = _sample_webhook_payload(
            phone_number_id=self.phone_number_id_a,
            wa_id="385911111111",
            wamid="wamid.inbound.route-a",
            body="Bok",
        )
        request = _signed_post(self.factory, self._url(), payload)
        with patch(
            "apps.integrations.whatsapp.whatsapp_guest_autocheckin.send_text_message"
        ) as mock_send:
            mock_send.return_value = {"messages": [{"id": "wamid.outbound.route-a"}]}
            response = WhatsAppWebhookView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        inbound = WhatsAppMessage.objects.get(wamid="wamid.inbound.route-a")
        self.assertEqual(inbound.tenant_id, self.tenant_a.id)
        self.assertEqual(inbound.integration_id, self.integration_a.id)
        mock_send.assert_called_once()

    def test_tenant_isolation(self):
        payload = _sample_webhook_payload(
            phone_number_id=self.phone_number_id_b,
            wa_id="385911111111",
            wamid="wamid.inbound.tenant-b",
            body="Hello",
        )
        request = _signed_post(self.factory, self._url(), payload)
        with patch(
            "apps.integrations.whatsapp.whatsapp_guest_autocheckin.send_text_message"
        ) as mock_send:
            mock_send.return_value = {"messages": [{"id": "wamid.outbound.tenant-b"}]}
            response = WhatsAppWebhookView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        inbound = WhatsAppMessage.objects.get(wamid="wamid.inbound.tenant-b")
        self.assertEqual(inbound.tenant_id, self.tenant_b.id)
        self.assertNotEqual(inbound.tenant_id, self.tenant_a.id)

        greeting = mock_send.call_args.kwargs["body"]
        self.assertIn("booking code", greeting.lower())

    def test_reservation_match_from_db(self):
        reservation = find_reservation_for_wa_id(
            tenant_id=self.tenant_a.id,
            wa_id="385911111111",
        )
        self.assertEqual(reservation.pk, self.reservation_a.pk)

    def test_greeting_hr_with_match(self):
        greeting = build_greeting(
            integration_row=self.integration_a,
            reservation=self.reservation_a,
            profile_name="Ana",
        )
        self.assertIn("Bok Ana Anić", greeting)
        self.assertIn("BCOM-9001", greeting)
        self.assertIn("Uzorita Apartments", greeting)

    def test_greeting_en_without_match(self):
        greeting = build_greeting(
            integration_row=self.integration_b,
            reservation=None,
            profile_name="John",
        )
        self.assertIn("Hi John", greeting)
        self.assertIn("booking code", greeting.lower())

    def test_resolver_finds_integration(self):
        resolved = find_whatsapp_integration(self.phone_number_id_a)
        self.assertEqual(resolved.pk, self.integration_a.pk)

    def test_signature_helper(self):
        payload = b'{"object":"whatsapp_business_account"}'
        signature = (
            "sha256="
            + hmac.new(TEST_APP_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        )
        request = self.factory.post(
            self._url(),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
        )
        self.assertTrue(verify_webhook_signature(request, raw_body=payload))

    def test_verify_subscription_helper(self):
        request = self.factory.get(
            self._url(),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": TEST_VERIFY_TOKEN,
                "hub.challenge": "challenge-text",
            },
        )
        self.assertEqual(verify_webhook_subscription(request), "challenge-text")

    @patch("apps.integrations.whatsapp.whatsapp_guest_autocheckin.send_text_message")
    def test_end_to_end_reply_links_reservation(self, mock_send):
        mock_send.return_value = {"messages": [{"id": "wamid.outbound.e2e"}]}
        payload = _sample_webhook_payload(
            phone_number_id=self.phone_number_id_a,
            wa_id="385911111111",
            wamid="wamid.inbound.e2e",
            body="Pozdrav",
        )
        request = _signed_post(self.factory, self._url(), payload)
        response = WhatsAppWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        inbound = WhatsAppMessage.objects.get(wamid="wamid.inbound.e2e")
        self.assertEqual(inbound.reservation_id, self.reservation_a.id)
        self.assertTrue(
            WhatsAppMessage.objects.filter(
                wamid="wamid.outbound.e2e",
                direction=WhatsAppMessage.Direction.OUTBOUND,
            ).exists()
        )
        greeting = mock_send.call_args.kwargs["body"]
        self.assertIn("BCOM-9001", greeting)

    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    @patch("apps.integrations.whatsapp.tasks.send_text_message")
    def test_inbound_push_when_auto_reply_disabled(self, mock_send, mock_notify):
        self.integration_a.set_config_dict(
            {
                **self.integration_a.get_config_dict(),
                "auto_reply": False,
            }
        )
        self.integration_a.save()

        payload = _sample_webhook_payload(
            phone_number_id=self.phone_number_id_a,
            wa_id="385911111111",
            wamid="wamid.inbound.no-autoreply",
            body="Imam pitanje o check-inu",
        )
        request = _signed_post(self.factory, self._url(), payload)
        response = WhatsAppWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        inbound = WhatsAppMessage.objects.get(wamid="wamid.inbound.no-autoreply")
        self.assertEqual(inbound.reservation_id, self.reservation_a.id)
        mock_send.assert_not_called()
        mock_notify.assert_called_once_with(
            self.reservation_a.pk,
            channel="whatsapp",
            body_preview="Imam pitanje o check-inu",
        )
