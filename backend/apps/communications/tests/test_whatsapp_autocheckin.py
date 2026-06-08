from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from apps.communications.whatsapp_autocheckin_tasks import (
    is_immediate_autocheckin_eligible,
    iter_due_autocheckin_reservations,
    maybe_send_immediate_autocheckin_welcome,
    run_whatsapp_autocheckin_welcome,
    send_welcome_template_for_reservation,
)
from apps.integrations.models import IntegrationConfig
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.integrations.whatsapp.welcome_template import build_welcome_template_parameters
from apps.properties.models import Property
from apps.reservations.booking_lifecycle import confirm_web_booking
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

TEST_D360_KEY = "test-d360-key"
ZAGREB = ZoneInfo("Europe/Zagreb")


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class WhatsAppAutocheckinWelcomeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="hr")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
            whatsapp_autocheckin_enabled=True,
            whatsapp_autocheckin_time=time(8, 0),
        )
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
                "whatsapp_templates": {
                    "header_image_url": "https://stay.hr/static/whatsapp-header.png",
                    "welcome": {"hr": "stay_welcome_hr", "en": "stay_welcome_en"},
                },
            }
        )
        self.integration.save()
        self.today = date(2026, 6, 7)
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ana Anić",
            booker_phone="+385911111111",
            booking_code="BCOM-100",
            check_in=self.today,
            check_out=self.today + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
        )

    def test_welcome_template_parameters(self):
        lang, params = build_welcome_template_parameters(self.reservation)
        self.assertEqual(lang, "hr")
        self.assertEqual(params[0], "Ana")
        self.assertEqual(params[1], "BCOM-100")
        self.assertEqual(params[2], "Uzorita")
        self.assertIn("2026-06-07", params[3])
        self.assertIn("2026-06-09", params[4])

    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_due_after_autocheckin_time(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 7, 8, 15, tzinfo=ZAGREB)
        due = iter_due_autocheckin_reservations()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].pk, self.reservation.pk)

    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_not_due_before_autocheckin_time(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 7, 7, 45, tzinfo=ZAGREB)
        due = iter_due_autocheckin_reservations()
        self.assertEqual(due, [])

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.communications.whatsapp_autocheckin_tasks.send_template_message")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_send_welcome_marks_sent(self, mock_now, mock_send):
        mock_now.return_value = datetime(2026, 6, 7, 9, 0, tzinfo=ZAGREB)
        mock_send.return_value = {"messages": [{"id": "wamid.welcome.1"}]}

        result = send_welcome_template_for_reservation(self.reservation)
        self.assertEqual(result["status"], "sent")
        self.reservation.refresh_from_db()
        self.assertIsNotNone(self.reservation.whatsapp_welcome_sent_at)
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["template_name"], "stay_welcome_hr")
        self.assertEqual(kwargs["body_parameters"][0], "Ana")

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.communications.whatsapp_autocheckin_tasks.send_template_message")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_idempotent_second_run(self, mock_now, mock_send):
        mock_now.return_value = datetime(2026, 6, 7, 9, 0, tzinfo=ZAGREB)
        mock_send.return_value = {"messages": [{"id": "wamid.welcome.1"}]}
        send_welcome_template_for_reservation(self.reservation)

        result = run_whatsapp_autocheckin_welcome()
        mock_send.assert_called_once()
        self.assertEqual(result["sent"], 0)

    def test_dry_run_does_not_send(self):
        result = send_welcome_template_for_reservation(self.reservation, dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.reservation.refresh_from_db()
        self.assertIsNone(self.reservation.whatsapp_welcome_sent_at)


@override_settings(
    STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class WhatsAppImmediateAutocheckinTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita", default_language="hr")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
            whatsapp_autocheckin_enabled=True,
            whatsapp_autocheckin_time=time(8, 0),
        )
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
                "whatsapp_templates": {
                    "welcome": {"hr": "stay_welcome_hr"},
                },
            }
        )
        self.integration.save()
        self.today = date(2026, 6, 7)

    def _create_reservation(self, **overrides):
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "booker_name": "Ana Anić",
            "booker_phone": "+385911111111",
            "booking_code": "BCOM-200",
            "check_in": self.today,
            "check_out": self.today + timedelta(days=2),
            "status": Reservation.Status.EXPECTED,
        }
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_eligible_after_autocheckin_time(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        reservation = self._create_reservation()
        self.assertTrue(is_immediate_autocheckin_eligible(reservation))

    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_not_eligible_before_autocheckin_time(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 7, 7, 0, tzinfo=ZAGREB)
        reservation = self._create_reservation()
        self.assertFalse(is_immediate_autocheckin_eligible(reservation))

    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_not_eligible_future_check_in(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        reservation = self._create_reservation(check_in=self.today + timedelta(days=1))
        self.assertFalse(is_immediate_autocheckin_eligible(reservation))

    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_not_eligible_when_disabled(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        self.property.whatsapp_autocheckin_enabled = False
        self.property.save(update_fields=["whatsapp_autocheckin_enabled", "updated_at"])
        reservation = self._create_reservation()
        self.assertFalse(is_immediate_autocheckin_eligible(reservation))

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.communications.whatsapp_autocheckin_tasks.send_template_message")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_immediate_task_sends_when_eligible(self, mock_now, mock_send):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        mock_send.return_value = {"messages": [{"id": "wamid.immediate.1"}]}
        reservation = self._create_reservation()

        result = maybe_send_immediate_autocheckin_welcome(reservation.pk)

        self.assertEqual(result["status"], "sent")
        mock_send.assert_called_once()

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.communications.whatsapp_autocheckin_tasks.send_template_message")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_immediate_task_skips_before_time(self, mock_now, mock_send):
        mock_now.return_value = datetime(2026, 6, 7, 7, 0, tzinfo=ZAGREB)
        reservation = self._create_reservation()

        result = maybe_send_immediate_autocheckin_welcome(reservation.pk)

        self.assertEqual(result["status"], "skipped")
        mock_send.assert_not_called()

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.communications.whatsapp_autocheckin_tasks.send_template_message")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_immediate_task_already_sent(self, mock_now, mock_send):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        reservation = self._create_reservation(
            whatsapp_welcome_sent_at=datetime(2026, 6, 7, 8, 30, tzinfo=ZAGREB),
        )

        result = maybe_send_immediate_autocheckin_welcome(reservation.pk)

        self.assertEqual(result["status"], "already_sent")
        mock_send.assert_not_called()

    @patch("apps.communications.whatsapp_autocheckin_tasks.maybe_send_immediate_autocheckin_welcome")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_post_save_queues_immediate_task(self, mock_now, mock_task):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        with self.captureOnCommitCallbacks(execute=True):
            reservation = self._create_reservation()
        mock_task.delay.assert_called_once_with(reservation.pk)

    @patch("apps.communications.whatsapp_autocheckin_tasks.maybe_send_immediate_autocheckin_welcome")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_post_save_skips_web_pending(self, mock_now, mock_task):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        with self.captureOnCommitCallbacks(execute=True):
            self._create_reservation(status=Reservation.Status.PENDING, source="api")
        mock_task.delay.assert_not_called()

    @patch("apps.communications.whatsapp_autocheckin_tasks.maybe_send_immediate_autocheckin_welcome")
    @patch("apps.core.tasks.notify_new_reservation")
    @patch("apps.communications.tasks.send_guest_booking_confirmed_email")
    @patch("apps.communications.whatsapp_autocheckin_tasks.property_local_now")
    def test_confirm_web_booking_queues_immediate_task(
        self,
        mock_now,
        mock_email,
        mock_notify,
        mock_task,
    ):
        mock_now.return_value = datetime(2026, 6, 7, 10, 0, tzinfo=ZAGREB)
        reservation = self._create_reservation(status=Reservation.Status.PENDING, source="api")

        self.assertTrue(confirm_web_booking(reservation.pk))
        mock_task.delay.assert_called_once_with(reservation.pk)
