from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.integrations.whatsapp.tasks import process_inbound_message
from apps.integrations.whatsapp.whatsapp_operator import (
    is_operator_wa_id,
    operator_name_for_wa_id,
)
from apps.integrations.whatsapp.whatsapp_operator_service import (
    OPERATOR_CHECKIN_BUTTON_ID,
    OPERATOR_CHECKIN_BUTTON_TITLE,
    _format_match_candidates,
    handle_operator_inbound,
    is_operator_checkin_command,
    is_operator_checkin_trigger,
)
from apps.properties.models import Property
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    DocumentIntakeJobStatus,
    WhatsAppOperatorSession,
    WhatsAppOperatorSessionStatus,
    Reservation,
)
from apps.tenants.models import Tenant, TenantReceptionSettings


@override_settings(
    STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class WhatsAppOperatorTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="hr")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            whatsapp_operator_phones=[
                {"name": "Toni Šupe", "phone": "+385998388513"},
                {"name": "Ante Vrcan", "phone": "+385976713511"},
            ],
        )
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
                "auto_reply": True,
            }
        )
        self.integration.save()
        self.operator_wa_id = "385998388513"
        self.other_reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ante Vrcan",
            booker_phone="+385976713511",
            booker_email="ante.test@example.com",
            adults_count=1,
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 3),
            status=Reservation.Status.EXPECTED,
        )
        self.target_reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Robert Siebinger",
            booker_phone="+4369912014899",
            booker_email="guest@example.com",
            adults_count=1,
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 3),
            status=Reservation.Status.EXPECTED,
            booking_code="UZO-TEST",
        )

    def test_operator_lookup(self):
        self.assertTrue(is_operator_wa_id(tenant_id=self.tenant.pk, wa_id="385998388513"))
        self.assertTrue(is_operator_wa_id(tenant_id=self.tenant.pk, wa_id="+385976713511"))
        self.assertFalse(is_operator_wa_id(tenant_id=self.tenant.pk, wa_id="385911111111"))
        self.assertEqual(
            operator_name_for_wa_id(tenant_id=self.tenant.pk, wa_id="385998388513"),
            "Toni Šupe",
        )

    def test_checkin_command_normalization(self):
        self.assertTrue(is_operator_checkin_command("check-in"))
        self.assertTrue(is_operator_checkin_command("check in"))
        self.assertTrue(is_operator_checkin_command("CHECKIN"))
        self.assertFalse(is_operator_checkin_command("auto check-in"))

    def test_checkin_trigger_button(self):
        self.assertTrue(is_operator_checkin_trigger(button_id=OPERATOR_CHECKIN_BUTTON_ID))
        self.assertTrue(is_operator_checkin_trigger(text="check-in"))
        self.assertFalse(is_operator_checkin_trigger(button_id="docs_all_yes"))

    @patch("apps.integrations.whatsapp.whatsapp_operator_service.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.fetch_whatsapp_media")
    def test_operator_image_collects_without_reservation_link(self, mock_fetch, mock_send):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        mock_send.return_value = {"messages": [{"id": "wamid.out.ack"}]}

        message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.op.image",
            wa_id=self.operator_wa_id,
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={
                "type": "image",
                "image": {"id": "media-op-1", "mime_type": "image/jpeg"},
            },
        )

        result = handle_operator_inbound(
            row=message,
            integration_row=self.integration,
            runtime=WhatsAppRuntimeConfig.from_integration_dict(self.integration.get_config_dict()),
            action_text="",
        )

        self.assertEqual(result["status"], "collected")
        message.refresh_from_db()
        self.assertIsNone(message.reservation_id)
        session = WhatsAppOperatorSession.objects.get(operator_wa_id=self.operator_wa_id)
        self.assertEqual(session.status, WhatsAppOperatorSessionStatus.COLLECTING)
        job = session.job
        self.assertEqual(job.source, DocumentIntakeJobSource.WHATSAPP_OPERATOR)
        self.assertIsNone(job.reservation_id)
        self.assertEqual(job.images.count(), 1)
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        self.assertEqual(
            kwargs["buttons"],
            [(OPERATOR_CHECKIN_BUTTON_ID, OPERATOR_CHECKIN_BUTTON_TITLE)],
        )
        self.assertIn("Pritisnite Check-in ako ste gotovi", kwargs["body"])
        self.assertIn("1 slika", kwargs["body"])

    @patch("apps.integrations.whatsapp.operator_job_complete.complete_operator_checkin_after_apply")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.apply_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.process_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.send_text_message")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.fetch_whatsapp_media")
    def test_operator_checkin_finalize(
        self,
        mock_fetch,
        mock_interactive,
        mock_send,
        mock_process,
        mock_apply,
        mock_finalize_after_apply,
    ):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        mock_interactive.return_value = {"messages": [{"id": "wamid.out.prompt"}]}
        mock_send.return_value = {"messages": [{"id": "wamid.out.success"}]}
        mock_apply.return_value = [{"guest_name": "Robert Siebinger"}]

        def _finalize_side_effect(**kwargs):
            session = kwargs.get("session")
            if session is not None:
                session.status = WhatsAppOperatorSessionStatus.DONE
                session.save(update_fields=["status", "updated_at"])
            return {
                "status": "completed",
                "job_id": kwargs["job"].pk,
                "reservation_id": self.target_reservation.pk,
                "guest_notify": {"channel": "whatsapp", "status": "sent"},
            }

        mock_finalize_after_apply.side_effect = _finalize_side_effect

        image_message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.op.image.1",
            wa_id=self.operator_wa_id,
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={
                "type": "image",
                "image": {"id": "media-op-1", "mime_type": "image/jpeg"},
            },
        )
        runtime = WhatsAppRuntimeConfig.from_integration_dict(self.integration.get_config_dict())
        handle_operator_inbound(
            row=image_message,
            integration_row=self.integration,
            runtime=runtime,
            action_text="",
        )

        session = WhatsAppOperatorSession.objects.get(operator_wa_id=self.operator_wa_id)
        job = session.job

        def _set_matches(job_id):
            DocumentIntakeJob.objects.filter(pk=job_id).update(
                status=DocumentIntakeJobStatus.DONE,
                matches=[
                    {
                        "auto_apply": True,
                        "guest_id": 1,
                        "reservation_id": self.target_reservation.pk,
                        "reservation_label": self.target_reservation.booking_code,
                        "guest_name": "Robert Siebinger",
                    }
                ],
            )

        mock_process.side_effect = _set_matches

        checkin_message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.op.checkin",
            wa_id=self.operator_wa_id,
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="check-in",
            raw_payload={"type": "text", "text": {"body": "check-in"}},
        )
        result = handle_operator_inbound(
            row=checkin_message,
            integration_row=self.integration,
            runtime=runtime,
            action_text="check-in",
        )

        self.assertEqual(result["status"], "completed")
        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppOperatorSessionStatus.DONE)
        mock_process.assert_called_once_with(job.pk)
        mock_apply.assert_called_once_with(job.pk)
        mock_finalize_after_apply.assert_called_once()
        job.refresh_from_db()
        self.assertEqual(job.reservation_id, self.target_reservation.pk)

    @patch("apps.integrations.whatsapp.operator_job_complete.complete_operator_checkin_after_apply")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.apply_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.process_document_intake_job")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.send_text_message")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.fetch_whatsapp_media")
    def test_operator_checkin_button_triggers_finalize(
        self,
        mock_fetch,
        mock_interactive,
        mock_send,
        mock_process,
        mock_apply,
        mock_finalize_after_apply,
    ):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        mock_interactive.return_value = {"messages": [{"id": "wamid.out.prompt"}]}
        mock_send.return_value = {"messages": [{"id": "wamid.out.success"}]}
        mock_apply.return_value = [{"guest_name": "Robert Siebinger"}]
        mock_finalize_after_apply.return_value = {
            "status": "completed",
            "job_id": 1,
            "reservation_id": self.target_reservation.pk,
        }

        image_message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.op.image.btn.1",
            wa_id=self.operator_wa_id,
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={
                "type": "image",
                "image": {"id": "media-op-btn-1", "mime_type": "image/jpeg"},
            },
        )
        runtime = WhatsAppRuntimeConfig.from_integration_dict(self.integration.get_config_dict())
        handle_operator_inbound(
            row=image_message,
            integration_row=self.integration,
            runtime=runtime,
            action_text="",
        )

        session = WhatsAppOperatorSession.objects.get(operator_wa_id=self.operator_wa_id)
        job = session.job

        def _set_matches(job_id):
            DocumentIntakeJob.objects.filter(pk=job_id).update(
                status=DocumentIntakeJobStatus.DONE,
                matches=[
                    {
                        "auto_apply": True,
                        "guest_id": 1,
                        "reservation_id": self.target_reservation.pk,
                        "reservation_label": self.target_reservation.booking_code,
                        "guest_name": "Robert Siebinger",
                    }
                ],
            )

        mock_process.side_effect = _set_matches

        checkin_message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.op.checkin.btn",
            wa_id=self.operator_wa_id,
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="interactive",
            body="Check-in",
            raw_payload={
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {
                        "id": OPERATOR_CHECKIN_BUTTON_ID,
                        "title": OPERATOR_CHECKIN_BUTTON_TITLE,
                    },
                },
            },
        )
        result = handle_operator_inbound(
            row=checkin_message,
            integration_row=self.integration,
            runtime=runtime,
            action_text=OPERATOR_CHECKIN_BUTTON_TITLE,
            button_id=OPERATOR_CHECKIN_BUTTON_ID,
        )

        self.assertEqual(result["status"], "completed")
        mock_process.assert_called_once_with(job.pk)
        mock_apply.assert_called_once_with(job.pk)

    @patch("apps.integrations.whatsapp.whatsapp_operator_service.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_operator_service.fetch_whatsapp_media")
    @patch("apps.integrations.whatsapp.tasks.on_whatsapp_document_received.delay")
    @patch("apps.integrations.whatsapp.tasks.find_reservation_for_wa_id")
    def test_process_inbound_routes_operator_before_guest_flow(
        self,
        mock_find_reservation,
        mock_guest_document,
        mock_fetch,
        mock_send,
    ):
        mock_fetch.return_value = (b"fake-image-bytes", "image/jpeg")
        mock_send.return_value = {"messages": [{"id": "wamid.out.ack"}]}
        mock_find_reservation.return_value = self.other_reservation

        ante_wa_id = "385976713511"
        message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.ante.image",
            wa_id=ante_wa_id,
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
            raw_payload={
                "type": "image",
                "image": {"id": "media-ante-1", "mime_type": "image/jpeg"},
            },
        )

        result = process_inbound_message(message.pk)

        self.assertEqual(result["status"], "collected")
        self.assertTrue(result.get("operator_flow"))
        mock_find_reservation.assert_not_called()
        mock_guest_document.assert_not_called()
        message.refresh_from_db()
        self.assertIsNone(message.reservation_id)


class OperatorMatchCandidateFormatTests(TestCase):
    def test_format_nested_candidates_with_person_names(self):
        formatted = _format_match_candidates(
            [
                {
                    "person_name": "Francois HARTWEG",
                    "reservation_id": None,
                    "candidates": [
                        {
                            "reservation_id": 8,
                            "guest_id": 1014,
                            "guest_name": "François Hartweg",
                            "reservation_label": "#8 · François Hartweg · 2026-06-09",
                            "match_type": "name",
                        },
                        {
                            "reservation_id": 138,
                            "guest_id": 1951,
                            "guest_name": "Novi gost",
                            "reservation_label": "#138 · Jasmin Engeland · 2026-06-10",
                            "match_type": "unfilled_slot",
                        },
                    ],
                }
            ]
        )
        self.assertIn("#8", formatted)
        self.assertIn("Francois HARTWEG", formatted)
        self.assertIn("[name]", formatted)
        self.assertIn("#138", formatted)
