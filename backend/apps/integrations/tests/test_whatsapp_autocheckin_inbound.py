from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.integrations.whatsapp.tasks import is_auto_checkin_quick_reply, process_inbound_message
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

TEST_D360_KEY = "test-d360-key"


@override_settings(
    STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class WhatsAppAutocheckinInboundTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="hr")
        self.property = Property.objects.create(tenant=self.tenant, name="Uzorita", slug="uzorita")
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="1068791909660300",
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "provider": "360dialog",
                "phone_number_id": "1068791909660300",
                "access_token": TEST_D360_KEY,
                "api_base_url": "https://waba-v2.360dialog.io",
                "auto_reply": True,
            }
        )
        self.integration.save()
        today = timezone.localdate()
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ana Anić",
            booker_phone="+385911111111",
            adults_count=2,
            check_in=today,
            check_out=today + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
        )

    def test_quick_reply_detection(self):
        self.assertTrue(is_auto_checkin_quick_reply("Auto check-in"))
        self.assertTrue(is_auto_checkin_quick_reply("Auto-Check-in"))
        self.assertFalse(is_auto_checkin_quick_reply("Bok"))

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.integrations.whatsapp.tasks.send_text_message")
    def test_template_button_sends_documents_text(self, mock_send):
        mock_send.return_value = {"messages": [{"id": "wamid.out.doc.button"}]}
        inbound = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.in.template.button",
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="button",
            body="",
            raw_payload={
                "type": "button",
                "button": {"text": "Auto check in", "payload": "Auto check in"},
            },
        )

        result = process_inbound_message(inbound.pk)

        self.assertEqual(result["status"], "documents_sent")
        mock_send.assert_called_once()
        self.reservation.refresh_from_db()
        self.assertIsNotNone(self.reservation.whatsapp_autocheckin_engaged_at)

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.integrations.whatsapp.tasks.send_text_message")
    def test_quick_reply_sends_documents_text(self, mock_send):
        mock_send.return_value = {"messages": [{"id": "wamid.out.doc"}]}
        inbound = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.in.quick",
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="interactive",
            body="Auto check-in",
            raw_payload={
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "1", "title": "Auto check-in"},
                },
            },
        )

        result = process_inbound_message(inbound.pk)

        self.assertEqual(result["status"], "documents_sent")
        mock_send.assert_called_once()
        self.reservation.refresh_from_db()
        self.assertIsNotNone(self.reservation.whatsapp_autocheckin_engaged_at)
        body = mock_send.call_args.kwargs["body"]
        self.assertIn("Check-in — dokumenti", body)
        self.assertIn("2", body)

    @patch("apps.integrations.whatsapp.tasks.send_text_message")
    @patch("apps.integrations.whatsapp.tasks.on_whatsapp_document_received.delay")
    def test_media_skips_auto_reply(self, mock_doc_task, mock_send):
        inbound = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.in.image",
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={"type": "image", "image": {"id": "media-1"}},
        )

        result = process_inbound_message(inbound.pk)

        self.assertEqual(result["status"], "auto_reply_skipped")
        mock_send.assert_not_called()
        mock_doc_task.assert_called_once_with(inbound.pk)
