from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.ai.provider import GuestComposeError
from apps.communications.guest_arrival_inbound import (
    classify_inbound,
    maybe_handle_guest_arrival_inbound,
    save_stated_arrival,
)
from apps.communications.guest_arrival_llm import ArrivalLlmResult
from apps.communications.guest_arrival_policy import (
    evaluate_arrival_time,
    is_late_arrival,
)
from apps.communications.guest_compose_language import detect_message_language
from apps.communications.models import GuestMessageDraft
from apps.properties.models import AfterHoursArrivalPolicy, Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

ZAGREB = ZoneInfo("Europe/Zagreb")


class GuestArrivalPolicyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="policy", name="Policy")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Test",
            slug="test",
            check_in_time=time(15, 0),
            check_in_latest_time=time(22, 0),
            timezone="Europe/Zagreb",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 6, 14),
            check_out=date(2026, 6, 16),
            status=Reservation.Status.EXPECTED,
        )

    def test_within_window(self):
        parsed = datetime(2026, 6, 14, 19, 30, tzinfo=ZAGREB)
        self.assertEqual(evaluate_arrival_time(self.reservation, parsed), "within")
        self.assertFalse(is_late_arrival(self.reservation, parsed))

    def test_late_arrival(self):
        parsed = datetime(2026, 6, 14, 23, 0, tzinfo=ZAGREB)
        self.assertEqual(evaluate_arrival_time(self.reservation, parsed), "late")
        self.assertTrue(is_late_arrival(self.reservation, parsed))

    def test_no_latest_limit(self):
        self.property.check_in_latest_time = None
        self.property.save(update_fields=["check_in_latest_time", "updated_at"])
        parsed = datetime(2026, 6, 14, 23, 0, tzinfo=ZAGREB)
        self.assertEqual(evaluate_arrival_time(self.reservation, parsed), "no_limit")


class GuestArrivalClassifyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="classify", name="Classify")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Test",
            slug="test",
            timezone="Europe/Zagreb",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 6, 14),
            check_out=date(2026, 6, 16),
            status=Reservation.Status.EXPECTED,
        )

    def test_time_stated(self):
        self.assertEqual(
            classify_inbound("Dolazimo oko 19:30", self.reservation),
            "time_stated",
        )

    def test_late_inquiry(self):
        self.assertEqual(
            classify_inbound("Možemo li doći kasnije?", self.reservation),
            "late_inquiry",
        )

    def test_unrelated(self):
        self.assertIsNone(classify_inbound("Hvala, vidimo se", self.reservation))


class GuestArrivalLanguageTests(TestCase):
    def test_detect_croatian(self):
        self.assertEqual(detect_message_language("Možemo li doći kasnije večeras?"), "hr")

    def test_detect_german(self):
        self.assertEqual(detect_message_language("Können wir spaeter ankommen?"), "de")

    def test_detect_english_default(self):
        self.assertEqual(detect_message_language("See you tomorrow"), "en")


class GuestArrivalInboundTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="inbound", name="Inbound")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
            check_in_time=time(15, 0),
            check_in_latest_time=time(22, 0),
            after_hours_arrival_policy=AfterHoursArrivalPolicy.CONTACT,
            after_hours_contact_phone="+385991234567",
            guest_arrival_auto_reply_enabled=True,
            timezone="Europe/Zagreb",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_email="guest@example.com",
            check_in=date(2026, 6, 14),
            check_out=date(2026, 6, 16),
            status=Reservation.Status.EXPECTED,
        )

    def test_save_stated_arrival(self):
        parsed = save_stated_arrival(self.reservation, text="oko 19:30")
        self.reservation.refresh_from_db()
        self.assertIsNotNone(parsed)
        self.assertEqual(self.reservation.guest_stated_arrival_text, "oko 19:30")
        self.assertIsNotNone(self.reservation.guest_stated_arrival_at)

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_arrival_inbound.schedule_arrival_confirm_prompt")
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    def test_handle_time_stated_sends_reply(self, mock_send, mock_schedule, _mock_llm):
        mock_send.return_value = object()
        mock_schedule.return_value = {"status": "scheduled"}

        result = maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Dolazimo oko 19:30",
            channel="email",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["kind"], "time_stated")
        self.assertFalse(result["used_llm"])
        mock_send.assert_called_once()
        self.reservation.refresh_from_db()
        self.assertIn("19:30", self.reservation.guest_stated_arrival_text)

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    def test_late_inquiry_reply(self, mock_send, _mock_llm):
        mock_send.return_value = object()

        result = maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Možemo li doći kasnije večeras?",
            channel="booking",
        )

        self.assertEqual(result["kind"], "late_inquiry")
        mock_send.assert_called_once()
        body = mock_send.call_args.kwargs["body_text"]
        self.assertIn("15:00", body)
        self.assertIn("22:00", body)

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    def test_late_time_contact_policy(self, mock_send, _mock_llm):
        mock_send.return_value = object()

        maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Dolazimo u 23:00",
            channel="whatsapp",
        )

        body = mock_send.call_args.kwargs["body_text"]
        self.assertIn("+385991234567", body)

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    def test_dedup_same_kind_same_day(self, mock_send, _mock_llm):
        mock_send.return_value = object()

        maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Možemo li doći kasnije?",
            channel="email",
        )
        maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Još jednom, kasniji dolazak?",
            channel="email",
        )

        self.assertEqual(mock_send.call_count, 1)

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    def test_fallback_on_llm_error(self, mock_send, _mock_llm):
        mock_send.return_value = object()
        with patch(
            "apps.communications.guest_arrival_inbound.llm_configured",
            return_value=True,
        ), patch(
            "apps.communications.guest_arrival_inbound.analyze_and_compose_arrival_reply",
            side_effect=GuestComposeError("timeout"),
        ):
            result = maybe_handle_guest_arrival_inbound(
                self.reservation,
                "Možemo li doći kasnije?",
                channel="email",
            )

        self.assertEqual(result["kind"], "late_inquiry")
        self.assertFalse(result["used_llm"])
        mock_send.assert_called_once()


class GuestArrivalLlmTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="llm", name="LLM")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
            check_in_time=time(15, 0),
            check_in_latest_time=time(22, 0),
            guest_arrival_auto_reply_enabled=True,
            timezone="Europe/Zagreb",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 6, 14),
            check_out=date(2026, 6, 16),
            status=Reservation.Status.EXPECTED,
        )

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=True)
    @patch("apps.communications.guest_arrival_inbound.schedule_arrival_confirm_prompt")
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    @patch("apps.communications.guest_arrival_inbound.analyze_and_compose_arrival_reply")
    def test_llm_time_stated(self, mock_analyze, mock_send, mock_schedule, _llm_on):
        mock_send.return_value = object()
        mock_schedule.return_value = {"status": "scheduled"}
        mock_analyze.return_value = ArrivalLlmResult(
            is_arrival_related=True,
            scenario="time_stated",
            reply_language="de",
            reply_text="Danke, wir haben 19:30 notiert.\n\nUzorita\n\nManaged by stay.hr — https://stay.hr/",
            stated_time_raw="19:30",
        )

        result = maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Wir kommen gegen 19:30",
            channel="email",
        )

        self.assertTrue(result["used_llm"])
        self.assertEqual(result["kind"], "time_stated")
        mock_send.assert_called_once()
        draft = GuestMessageDraft.objects.get(reservation=self.reservation)
        self.assertEqual(draft.language, "de")
        self.assertTrue(draft.llm_model)

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=True)
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    @patch("apps.communications.guest_arrival_inbound.analyze_and_compose_arrival_reply")
    def test_llm_late_inquiry(self, mock_analyze, mock_send, _llm_on):
        mock_send.return_value = object()
        mock_analyze.return_value = ArrivalLlmResult(
            is_arrival_related=True,
            scenario="late_inquiry",
            reply_language="en",
            reply_text="Check-in is from 15:00 to 22:00. What time will you arrive?",
            stated_time_raw="",
        )

        result = maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Can we arrive later?",
            channel="booking",
        )

        self.assertEqual(result["kind"], "late_inquiry")
        self.assertTrue(result["used_llm"])
        mock_send.assert_called_once()

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=True)
    @patch("apps.communications.guest_arrival_inbound.analyze_and_compose_arrival_reply")
    def test_llm_not_arrival_returns_none(self, mock_analyze, _llm_on):
        mock_analyze.return_value = ArrivalLlmResult(
            is_arrival_related=False,
            scenario=None,
            reply_language="en",
            reply_text="",
            stated_time_raw="",
        )

        result = maybe_handle_guest_arrival_inbound(
            self.reservation,
            "Thanks, see you!",
            channel="whatsapp",
        )

        self.assertIsNone(result)


class GuestArrivalEmailIntegrationTests(TestCase):
    def setUp(self):
        from apps.communications.guest_email_ingest import ParsedGuestEmail

        self.tenant = Tenant.objects.create(slug="email-arrival", name="Email Arrival")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Test",
            slug="test",
            check_in_time=time(15, 0),
            check_in_latest_time=time(22, 0),
            guest_arrival_auto_reply_enabled=True,
            timezone="Europe/Zagreb",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="1234567890",
            booker_email="guest@example.com",
            check_in=date(2026, 6, 14),
            check_out=date(2026, 6, 16),
            status=Reservation.Status.EXPECTED,
        )
        self.parsed = ParsedGuestEmail(
            message_id="arrival-test@example.com",
            raw_from="guest@example.com",
            from_email="guest@example.com",
            subject="Re: Booking",
            booking_code="1234567890",
            body_text="Dolazimo oko 19:30",
            received_at=datetime(2026, 6, 14, 10, 0, tzinfo=ZAGREB),
        )

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=False)
    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    def test_email_ingest_saves_arrival(self, mock_send, mock_notify, _mock_llm):
        from apps.communications.guest_email_ingest import ingest_parsed_email

        mock_send.return_value = object()

        ingest_parsed_email(self.tenant, self.parsed, notify=True)

        self.reservation.refresh_from_db()
        self.assertIn("19:30", self.reservation.guest_stated_arrival_text)
        mock_send.assert_called_once()
        mock_notify.assert_called_once()


class GuestArrivalChannexIntegrationTests(TestCase):
    def setUp(self):
        from apps.integrations.channex.booking_service import channex_external_id
        from apps.integrations.models import IntegrationConfig
        from apps.tenants.models import ChannelManager, TenantReceptionSettings

        self.tenant = Tenant.objects.create(slug="cx-arrival", name="Channex Arrival")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Test",
            slug="test",
            check_in_time=time(15, 0),
            check_in_latest_time=time(22, 0),
            guest_arrival_auto_reply_enabled=True,
            timezone="Europe/Zagreb",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {"property_id": "prop-uuid", "sync_property_slug": "test"}
        )
        self.integration.save()
        self.booking_id = "booking-arrival-1"
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id=channex_external_id(self.booking_id),
            import_source="channex",
            check_in=date(2026, 6, 14),
            check_out=date(2026, 6, 16),
            status=Reservation.Status.EXPECTED,
        )

    @patch("apps.communications.guest_arrival_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_arrival_inbound.send_guest_message")
    def test_channex_guest_message_triggers_late_inquiry_reply(self, mock_send, _mock_llm):
        from apps.integrations.channex.webhook_service import record_channex_webhook

        mock_send.return_value = object()
        payload = {
            "id": "msg-arrival-1",
            "message": "Can we arrive later in the evening?",
            "sender": "guest",
            "booking_id": self.booking_id,
            "message_thread_id": "thread-1",
            "attachments": [],
            "have_attachment": False,
        }

        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="message",
            property_id="prop-uuid",
            body={"payload": payload},
        )

        mock_send.assert_called_once()
        body = mock_send.call_args.kwargs["body_text"]
        self.assertIn("15:00", body)
        self.assertIn("22:00", body)
