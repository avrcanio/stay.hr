from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.integrations.whatsapp.document_intake_task import process_whatsapp_document_message
from apps.properties.models import Property
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus, Reservation
from apps.tenants.models import Tenant


@override_settings(
    STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY,
    CELERY_TASK_ALWAYS_EAGER=True,
)
class WhatsAppDocumentIntakeTaskTests(TestCase):
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
                "access_token": "d360-test",
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
        self.message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.inbound.image",
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={"type": "image", "image": {"id": "media-123", "mime_type": "image/jpeg"}},
        )

    @patch("apps.integrations.whatsapp.document_intake_task.apply_document_intake_job")
    @patch("apps.integrations.whatsapp.document_intake_task.process_document_intake_job")
    @patch("apps.integrations.whatsapp.document_intake_task.fetch_whatsapp_media")
    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    def test_creates_job_and_runs_ocr(self, mock_notify, mock_fetch, mock_process, mock_apply):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")

        def _finish_ocr(job_id):
            job = DocumentIntakeJob.objects.get(pk=job_id)
            job.status = DocumentIntakeJobStatus.DONE
            job.matches = [{"auto_apply": True, "guest_id": 1, "person_index": 0, "reservation_id": self.reservation.pk}]
            job.save(update_fields=["status", "matches", "updated_at"])

        mock_process.side_effect = _finish_ocr
        mock_apply.return_value = [{"guest_id": 1, "reservation_id": self.reservation.pk}]

        result = process_whatsapp_document_message(self.message.pk)

        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["apply"]["status"], "applied")
        job = DocumentIntakeJob.objects.get(pk=result["job_id"])
        self.assertEqual(job.reservation_id, self.reservation.pk)
        self.assertEqual(job.source, "whatsapp")
        self.assertEqual(job.images.count(), 1)
        mock_process.assert_called_once_with(job.pk)
        mock_apply.assert_called_once_with(job.pk)
        mock_notify.assert_called_once()

    @patch("apps.integrations.whatsapp.document_intake_task.process_document_intake_job")
    @patch("apps.integrations.whatsapp.document_intake_task.fetch_whatsapp_media")
    def test_skips_duplicate_job(self, mock_fetch, mock_process):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        process_whatsapp_document_message(self.message.pk)
        result = process_whatsapp_document_message(self.message.pk)
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(DocumentIntakeJob.objects.filter(whatsapp_message=self.message).count(), 1)
