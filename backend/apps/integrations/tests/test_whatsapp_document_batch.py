from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.integrations.whatsapp.whatsapp_document_batch import (
    AFTER_NO_SECONDS,
    CONFIRM_TIMEOUT_SECONDS,
    QUIET_SECONDS,
    document_batch_after_no_quiet,
    document_batch_confirm_timeout,
    document_batch_quiet_elapsed,
    finalize_whatsapp_document_batch,
    handle_whatsapp_document_batch_reply,
    is_documents_all_no_reply,
    is_documents_all_yes_reply,
    on_whatsapp_document_received,
)
from apps.properties.models import Property
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobStatus,
    WhatsAppDocumentBatchSession,
    WhatsAppDocumentBatchStatus,
    Reservation,
)
from apps.tenants.models import Tenant


@override_settings(
    STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class WhatsAppDocumentBatchTests(TestCase):
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
            adults_count=2,
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 3),
            status=Reservation.Status.EXPECTED,
        )

    def _image_message(self, *, pk_suffix: str, wamid: str) -> WhatsAppMessage:
        return WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid=wamid,
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={
                "type": "image",
                "image": {"id": f"media-{pk_suffix}", "mime_type": "image/jpeg"},
            },
        )

    def test_reply_detection(self):
        self.assertTrue(is_documents_all_yes_reply(button_id="docs_all_yes"))
        self.assertTrue(is_documents_all_yes_reply(text="Da"))
        self.assertTrue(is_documents_all_yes_reply(text="Yes"))
        self.assertTrue(is_documents_all_no_reply(button_id="docs_all_no"))
        self.assertTrue(is_documents_all_no_reply(text="Ne"))
        self.assertFalse(is_documents_all_yes_reply(text="Auto check-in"))

    @patch("apps.integrations.whatsapp.whatsapp_document_batch._schedule_task")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.fetch_whatsapp_media")
    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    def test_three_images_one_job_before_finalize(self, mock_notify, mock_fetch, mock_schedule):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        messages = [self._image_message(pk_suffix=str(i), wamid=f"wamid.in.{i}") for i in range(3)]

        for message in messages:
            result = on_whatsapp_document_received(message.pk)
            self.assertEqual(result["status"], "collected")

        session = WhatsAppDocumentBatchSession.objects.get(reservation=self.reservation)
        self.assertEqual(session.status, WhatsAppDocumentBatchStatus.COLLECTING)
        self.assertEqual(session.job.images.count(), 3)
        self.assertEqual(DocumentIntakeJob.objects.filter(reservation=self.reservation).count(), 1)
        mock_notify.assert_not_called()

    @patch("apps.integrations.whatsapp.whatsapp_document_batch.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch._schedule_task")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.fetch_whatsapp_media")
    def test_quiet_elapsed_sends_interactive_prompt(self, mock_fetch, mock_schedule, mock_send):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        mock_send.return_value = {"messages": [{"id": "wamid.out.prompt"}]}
        message = self._image_message(pk_suffix="1", wamid="wamid.in.1")
        on_whatsapp_document_received(message.pk)

        session = WhatsAppDocumentBatchSession.objects.get(reservation=self.reservation)
        session.last_media_at = timezone.now() - timezone.timedelta(seconds=QUIET_SECONDS + 1)
        session.save(update_fields=["last_media_at", "updated_at"])

        result = document_batch_quiet_elapsed(session.pk)

        self.assertEqual(result["status"], "prompted")
        mock_send.assert_called_once()
        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppDocumentBatchStatus.AWAITING_CONFIRM)
        self.assertEqual(session.prompt_count, 1)

    @patch("apps.integrations.whatsapp.whatsapp_document_batch.apply_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.process_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch._schedule_task")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.fetch_whatsapp_media")
    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    def test_yes_finalizes_once(
        self,
        mock_notify,
        mock_fetch,
        mock_schedule,
        mock_send,
        mock_process,
        mock_apply,
    ):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        mock_send.return_value = {"messages": [{"id": "wamid.out.prompt"}]}

        def _finish_ocr(job_id):
            job = DocumentIntakeJob.objects.get(pk=job_id)
            job.status = DocumentIntakeJobStatus.DONE
            job.matches = [
                {"auto_apply": True, "guest_id": 1, "person_index": 0, "reservation_id": self.reservation.pk}
            ]
            job.save(update_fields=["status", "matches", "updated_at"])

        mock_process.side_effect = _finish_ocr
        mock_apply.return_value = [{"guest_id": 1, "reservation_id": self.reservation.pk}]

        message = self._image_message(pk_suffix="1", wamid="wamid.in.yes")
        on_whatsapp_document_received(message.pk)
        session = WhatsAppDocumentBatchSession.objects.get(reservation=self.reservation)
        session.status = WhatsAppDocumentBatchStatus.AWAITING_CONFIRM
        session.save(update_fields=["status", "updated_at"])

        yes_message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.in.yes.reply",
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="interactive",
            body="",
            raw_payload={
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "docs_all_yes", "title": "Da"},
                },
            },
        )

        result = handle_whatsapp_document_batch_reply(yes_message.pk)

        self.assertEqual(result["status"], "finalized")
        mock_process.assert_called_once()
        mock_apply.assert_called_once()
        mock_notify.assert_called_once()
        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppDocumentBatchStatus.DONE)

    @patch("apps.integrations.whatsapp.whatsapp_document_batch.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch._schedule_task")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.fetch_whatsapp_media")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.apply_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.process_document_intake_job")
    def test_no_then_quiet_reprompts(self, mock_process, mock_apply, mock_fetch, mock_schedule, mock_send):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        mock_send.return_value = {"messages": [{"id": "wamid.out.prompt"}]}

        message = self._image_message(pk_suffix="1", wamid="wamid.in.no")
        on_whatsapp_document_received(message.pk)
        session = WhatsAppDocumentBatchSession.objects.get(reservation=self.reservation)
        session.status = WhatsAppDocumentBatchStatus.AWAITING_CONFIRM
        session.save(update_fields=["status", "updated_at"])

        no_message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.in.no.reply",
            wa_id="385911111111",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="interactive",
            body="",
            raw_payload={
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "docs_all_no", "title": "Ne"},
                },
            },
        )

        result = handle_whatsapp_document_batch_reply(no_message.pk)
        self.assertEqual(result["status"], "after_no")
        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppDocumentBatchStatus.AFTER_NO)

        result = document_batch_after_no_quiet(session.pk)
        self.assertEqual(result["status"], "prompted")
        self.assertEqual(mock_send.call_count, 1)
        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppDocumentBatchStatus.AWAITING_CONFIRM)
        self.assertEqual(session.prompt_count, 1)

    @patch("apps.integrations.whatsapp.whatsapp_document_batch._schedule_task")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.fetch_whatsapp_media")
    def test_new_image_during_after_no_resets_collecting(self, mock_fetch, mock_schedule):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        message = self._image_message(pk_suffix="1", wamid="wamid.in.reset")
        on_whatsapp_document_received(message.pk)
        session = WhatsAppDocumentBatchSession.objects.get(reservation=self.reservation)
        session.status = WhatsAppDocumentBatchStatus.AFTER_NO
        session.after_no_at = timezone.now() - timezone.timedelta(seconds=5)
        session.save(update_fields=["status", "after_no_at", "updated_at"])

        message2 = self._image_message(pk_suffix="2", wamid="wamid.in.reset2")
        result = on_whatsapp_document_received(message2.pk)

        self.assertEqual(result["status"], "collected")
        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppDocumentBatchStatus.COLLECTING)
        self.assertEqual(session.job.images.count(), 2)

    @patch("apps.integrations.whatsapp.whatsapp_document_batch.apply_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.process_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch._schedule_task")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.fetch_whatsapp_media")
    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    def test_confirm_timeout_finalizes(
        self,
        mock_notify,
        mock_fetch,
        mock_schedule,
        mock_process,
        mock_apply,
    ):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        message = self._image_message(pk_suffix="1", wamid="wamid.in.timeout")
        on_whatsapp_document_received(message.pk)
        session = WhatsAppDocumentBatchSession.objects.get(reservation=self.reservation)
        session.status = WhatsAppDocumentBatchStatus.AWAITING_CONFIRM
        session.prompt_sent_at = timezone.now() - timezone.timedelta(seconds=CONFIRM_TIMEOUT_SECONDS + 1)
        session.save(update_fields=["status", "prompt_sent_at", "updated_at"])

        result = document_batch_confirm_timeout(session.pk)

        self.assertEqual(result["status"], "finalized")
        mock_process.assert_called_once()
        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppDocumentBatchStatus.DONE)
        mock_notify.assert_called_once()

    @patch("apps.integrations.whatsapp.whatsapp_document_batch._schedule_task")
    @patch("apps.integrations.whatsapp.whatsapp_document_batch.fetch_whatsapp_media")
    def test_duplicate_message_skipped(self, mock_fetch, mock_schedule):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        message = self._image_message(pk_suffix="dup", wamid="wamid.in.dup")
        on_whatsapp_document_received(message.pk)
        result = on_whatsapp_document_received(message.pk)
        self.assertEqual(result["status"], "duplicate")
        session = WhatsAppDocumentBatchSession.objects.get(reservation=self.reservation)
        self.assertEqual(session.job.images.count(), 1)


class WhatsAppDocumentBatchTimerTests(TestCase):
    def test_schedule_task_uses_unique_ids_and_tracks_in_cache(self):
        from django.core.cache import cache

        from apps.integrations.whatsapp import whatsapp_document_batch as batch

        cache.clear()
        seen_ids: list[str] = []

        class FakeTask:
            def apply_async(self, *, args, countdown, task_id):
                seen_ids.append(task_id)
                return task_id

        fake = FakeTask()
        batch._schedule_task(task=fake, session_id=7, countdown=10, suffix="quiet")
        batch._schedule_task(task=fake, session_id=7, countdown=10, suffix="quiet")

        self.assertEqual(len(seen_ids), 2)
        self.assertNotEqual(seen_ids[0], seen_ids[1])
        self.assertTrue(all(task_id.startswith("wa-doc-quiet-7-") for task_id in seen_ids))
        self.assertEqual(cache.get(batch._timer_cache_key(7, "quiet")), seen_ids[1])

    @patch("config.celery.app.control.revoke")
    def test_revoke_scheduled_only_revokes_tracked_task(self, mock_revoke):
        from django.core.cache import cache

        from apps.integrations.whatsapp import whatsapp_document_batch as batch

        cache.clear()
        cache.set(batch._timer_cache_key(3, "quiet"), "wa-doc-quiet-3-abc123", timeout=60)

        batch._revoke_scheduled(3, "quiet")

        mock_revoke.assert_called_once_with("wa-doc-quiet-3-abc123", terminate=False)
        self.assertIsNone(cache.get(batch._timer_cache_key(3, "quiet")))
