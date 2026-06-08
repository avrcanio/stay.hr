from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from apps.integrations.models import IntegrationConfig
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.integrations.whatsapp.whatsapp_guest_autocheckin import (
    GUEST_AUTO_CHECKIN_BUTTON_ID,
    extract_booking_code_from_text,
    find_reservation_by_booking_code,
    handle_guest_autocheckin_inbound,
    is_guest_auto_checkin_button,
)
from apps.integrations.models import WhatsAppMessage
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig
from apps.properties.models import Property
from apps.reservations.models import Reservation, WhatsAppGuestAutocheckinSession
from apps.tenants.models import Tenant

TEST_D360_KEY = "test-d360-key"
ZAGREB = ZoneInfo("Europe/Zagreb")


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class WhatsAppGuestAutocheckinTests(TestCase):
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
            }
        )
        self.integration.save()
        self.runtime = WhatsAppRuntimeConfig.from_integration_dict(self.integration.get_config_dict())
        self.today = date(2026, 6, 7)
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ana Anić",
            booker_phone="+385922222222",
            booking_code="BCOM-777",
            check_in=self.today,
            check_out=self.today + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
        )

    def test_extract_booking_code(self):
        self.assertEqual(extract_booking_code_from_text("BCOM-777"), "BCOM-777")
        self.assertEqual(extract_booking_code_from_text("Kod je 1234567890"), "1234567890")
        self.assertIsNone(extract_booking_code_from_text("bok"))

    def test_find_reservation_by_booking_code(self):
        found = find_reservation_by_booking_code(tenant_id=self.tenant.pk, code="bcom-777")
        self.assertEqual(found.pk, self.reservation.pk)

    def test_guest_auto_checkin_button_id(self):
        self.assertTrue(
            is_guest_auto_checkin_button(button_id=GUEST_AUTO_CHECKIN_BUTTON_ID, text="")
        )
        self.assertTrue(is_guest_auto_checkin_button(text="Auto check-in"))

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.integrations.whatsapp.whatsapp_guest_autocheckin.send_text_message")
    def test_unknown_phone_asks_for_booking_code(self, mock_send):
        mock_send.return_value = {"messages": [{"id": "wamid.out.ask"}]}
        inbound = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.hello",
            wa_id="385933333333",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="Bok",
            raw_payload={"type": "text", "text": {"body": "Bok"}},
        )

        result = handle_guest_autocheckin_inbound(
            row=inbound,
            integration_row=self.integration,
            runtime=self.runtime,
            action_text="Bok",
            reservation=None,
        )

        self.assertEqual(result["status"], "sent")
        mock_send.assert_called_once()
        body = mock_send.call_args.kwargs["body"]
        self.assertIn("booking kod", body.lower())
        self.assertTrue(
            WhatsAppGuestAutocheckinSession.objects.filter(
                tenant_id=self.tenant.pk,
                wa_id="385933333333",
            ).exists()
        )

    @patch.dict("os.environ", {"D360_API_KEY": TEST_D360_KEY})
    @patch("apps.integrations.whatsapp.whatsapp_guest_autocheckin.send_interactive_button_message")
    @patch("apps.integrations.whatsapp.whatsapp_guest_autocheckin.property_local_now")
    def test_booking_code_resolves_and_sends_prompt(self, mock_now, mock_send):
        mock_now.return_value = datetime(2026, 6, 7, 9, 0, tzinfo=ZAGREB)
        mock_send.return_value = {"messages": [{"id": "wamid.out.prompt"}]}
        inbound = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            wamid="wamid.in.code",
            wa_id="385933333333",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="BCOM-777",
            raw_payload={"type": "text", "text": {"body": "BCOM-777"}},
        )

        result = handle_guest_autocheckin_inbound(
            row=inbound,
            integration_row=self.integration,
            runtime=self.runtime,
            action_text="BCOM-777",
            reservation=None,
        )

        self.assertEqual(result["status"], "autocheckin_prompt_sent")
        inbound.refresh_from_db()
        self.reservation.refresh_from_db()
        self.assertEqual(inbound.reservation_id, self.reservation.pk)
        self.assertIsNotNone(self.reservation.whatsapp_autocheckin_engaged_at)
        mock_send.assert_called_once()
        buttons = mock_send.call_args.kwargs["buttons"]
        self.assertEqual(buttons[0][0], GUEST_AUTO_CHECKIN_BUTTON_ID)
