from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.communications.guest_compose import render_checkin_ready_message
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.apply_reply import maybe_send_document_apply_whatsapp_reply
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.properties.models import Property
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobSource, DocumentIntakeJobStatus, Reservation
from apps.tenants.models import Tenant

TEST_D360_KEY = "test-d360-key"


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class WhatsAppApplyReplyTests(TestCase):
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
                "auto_reply": False,
            }
        )
        self.integration.save()

        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ana Anić",
            booker_phone="+385911111111",
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 3),
            status=Reservation.Status.EXPECTED,
        )
        self.inbound = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.inbound.doc",
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={"type": "image", "image": {"id": "media-1"}},
        )
        self.job = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            whatsapp_message=self.inbound,
            source=DocumentIntakeJobSource.WHATSAPP,
            status=DocumentIntakeJobStatus.APPLIED,
        )

    @patch.dict("os.environ", {"WHATSAPP_DOCUMENT_APPLY_REPLY": "true", "D360_API_KEY": TEST_D360_KEY})
    @patch("apps.integrations.whatsapp.apply_reply.send_text_message")
    def test_sends_checkin_ready_after_apply(self, mock_send):
        mock_send.return_value = {"messages": [{"id": "wamid.outbound.ready"}]}
        applied = [{"guest_id": 1, "reservation_id": self.reservation.pk}]

        result = maybe_send_document_apply_whatsapp_reply(self.job, applied=applied)

        self.assertEqual(result["status"], "sent")
        mock_send.assert_called_once()
        body = mock_send.call_args.kwargs["body"]
        self.assertIn("Hvala vam na poslanim dokumentima", body)
        self.job.refresh_from_db()
        self.assertTrue(self.job.whatsapp_reply_sent)
        self.assertTrue(
            WhatsAppMessage.objects.filter(
                direction=WhatsAppMessage.Direction.OUTBOUND,
                reservation=self.reservation,
            ).exists()
        )

    @patch.dict("os.environ", {"WHATSAPP_DOCUMENT_APPLY_REPLY": "true"})
    def test_skips_duplicate_reply(self):
        self.job.whatsapp_reply_sent = True
        self.job.save(update_fields=["whatsapp_reply_sent"])
        result = maybe_send_document_apply_whatsapp_reply(
            self.job,
            applied=[{"guest_id": 1, "reservation_id": self.reservation.pk}],
        )
        self.assertEqual(result["status"], "already_sent")

    @patch.dict("os.environ", {"WHATSAPP_DOCUMENT_APPLY_REPLY": "true", "D360_API_KEY": TEST_D360_KEY})
    @patch("apps.integrations.whatsapp.apply_reply.send_text_message")
    def test_skips_when_sibling_job_already_sent_reply(self, mock_send):
        sibling = DocumentIntakeJob.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            source=DocumentIntakeJobSource.WHATSAPP,
            status=DocumentIntakeJobStatus.APPLIED,
            whatsapp_reply_sent=True,
        )
        self.assertIsNotNone(sibling.pk)
        result = maybe_send_document_apply_whatsapp_reply(
            self.job,
            applied=[{"guest_id": 1, "reservation_id": self.reservation.pk}],
        )
        self.assertEqual(result["status"], "already_sent")
        mock_send.assert_not_called()

    def test_render_checkin_ready_hr(self):
        text = render_checkin_ready_message(self.reservation)
        self.assertIn("Hvala vam na poslanim dokumentima", text)
