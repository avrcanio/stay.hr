from decimal import Decimal
import os
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class ReceptionGuestMessagesAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Luxury Room Uzorita",
            slug="uzorita",
            address="Ul. bana Josipa Jelačića 58, 22000 Šibenik",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="Deluxe King Room R1",
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5036489024",
            booking_code="5036489024",
            check_in="2026-06-04",
            check_out="2026-06-05",
            status=Reservation.Status.EXPECTED,
            booker_name="Wolfgang Gross",
            booker_email="wolfgang@example.com",
            booker_phone="+49 170 1234567",
            amount=Decimal("180.15"),
            adults_count=2,
            payment_provider="booking.com",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="Deluxe King Room R1",
            sort_order=0,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Wolfgang",
            last_name="Gross",
            email="wolfgang@example.com",
            is_primary=True,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}
        self.base = f"/api/v1/reception/reservations/{self.reservation.id}/messages"

    def test_list_messages_empty(self):
        response = self.client.get(f"{self.base}/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_checkin_fallback(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.booker_country = "HR"
        self.reservation.save(update_fields=["booker_country"])
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("draft_id", data)
        self.assertIn("Wolfgang", data["body_text"])
        self.assertFalse(data["llm_used"])
        body = data["body_text"]
        self.assertIn("Restaurant Uzorita", body)
        self.assertIn("Parkiranje", body)
        self.assertIn("eVisitor", body)
        self.assertNotIn("okvirno vrijeme dolaska", body.lower())
        self.assertTrue(data["channels"]["email"]["available"])
        self.assertEqual(data["channels"]["email"]["to"], "wolfgang@example.com")
        self.assertTrue(data["channels"]["whatsapp"]["available"])
        self.assertIn("491701234567", data["channels"]["whatsapp"]["phone_wa"])

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_checkin_language_de(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.booker_country = "DE"
        self.reservation.save(update_fields=["booker_country"])
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["language"], "de")
        self.assertIn("Eingang", data["body_text"])
        self.assertIn("Parken", data["body_text"])

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_checkin_language_balkan_hr(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.booker_country = "RS"
        self.reservation.save(update_fields=["booker_country"])
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["language"], "hr")
        self.assertIn("Parkiranje", data["body_text"])

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_checkin_language_default_en(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.booker_country = "NL"
        self.reservation.save(update_fields=["booker_country"])
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["language"], "en")
        self.assertIn("Parking", data["body_text"])

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_reply_checkin_ready(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.booker_country = "DE"
        self.reservation.save(update_fields=["booker_country"])
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "reply", "hint": "checkin ready"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertFalse(data["llm_used"])
        self.assertEqual(data["language"], "de")
        body = data["body_text"]
        self.assertIn("Vielen Dank", body)
        self.assertIn("Ankunftszeit", body)

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_reply_checkin_ready_language_es(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.booker_country = "ES"
        self.reservation.save(update_fields=["booker_country"])
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "reply", "hint": "checkin ready"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertFalse(data["llm_used"])
        self.assertEqual(data["language"], "es")
        self.assertIn("Gracias", data["body_text"])
        self.assertIn("llegada", data["body_text"])

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_reply_checkin_ready_same_lang_as_checkin(self):
        """RO guest → en for both checkin and checkin-ready reply."""
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.booker_country = "RO"
        self.reservation.save(update_fields=["booker_country"])
        checkin = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        reply = self.client.post(
            f"{self.base}/compose/",
            {"intent": "reply", "hint": "checkin ready"},
            format="json",
            **self.auth,
        )
        self.assertEqual(checkin.json()["language"], "en")
        self.assertEqual(reply.json()["language"], "en")
        self.assertIn("Parking", checkin.json()["body_text"])
        self.assertIn("Thank you", reply.json()["body_text"])

    @patch("apps.communications.guest_compose.complete_chat")
    @patch.dict(
        os.environ,
        {
            "GUEST_COMPOSE_LLM_PROVIDER": "openai",
            "GUEST_COMPOSE_LLM_API_KEY": "test-key",
            "GUEST_COMPOSE_LLM_MODEL": "gpt-4o-mini",
        },
        clear=False,
    )
    def test_compose_checkin_skips_llm(self, mock_complete):
        mock_complete.return_value = "LLM should not be used for checkin."
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertFalse(data["llm_used"])
        self.assertIn("Restaurant Uzorita", data["body_text"])
        mock_complete.assert_not_called()

    @patch("apps.communications.guest_compose.complete_chat")
    @patch.dict(
        os.environ,
        {
            "GUEST_COMPOSE_LLM_PROVIDER": "openai",
            "GUEST_COMPOSE_LLM_API_KEY": "test-key",
            "GUEST_COMPOSE_LLM_MODEL": "gpt-4o-mini",
        },
        clear=False,
    )
    def test_compose_uses_llm(self, mock_complete):
        mock_complete.return_value = "Hello Wolfgang!\n\nManaged by stay.hr — https://stay.hr/"
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "custom", "hint": "Confirm late arrival at 22:00."},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["llm_used"])
        self.assertIn("Hello Wolfgang", data["body_text"])
        mock_complete.assert_called_once()

    @patch("apps.communications.guest_message_send.send_guest_text_email")
    @patch.dict(os.environ, {}, clear=False)
    def test_send_email(self, mock_send):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        mock_send.return_value = {"sent": True, "to": "wolfgang@example.com"}
        compose = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        draft_id = compose.json()["draft_id"]
        body = "Custom check-in text for Wolfgang."

        response = self.client.post(
            f"{self.base}/send/",
            {
                "draft_id": draft_id,
                "channel": "email",
                "body_text": body,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["channel"], "email")
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["body_text"], body)
        mock_send.assert_called_once()

        timeline = self.client.get(f"{self.base}/", **self.auth)
        self.assertEqual(len(timeline.json()), 1)

    @patch.dict(os.environ, {}, clear=False)
    def test_send_whatsapp_handoff(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        compose = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        draft_id = compose.json()["draft_id"]
        body = "Bok Wolfgang! Check-in info."

        response = self.client.post(
            f"{self.base}/send/",
            {
                "draft_id": draft_id,
                "channel": "whatsapp",
                "body_text": body,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["channel"], "whatsapp")
        self.assertEqual(data["status"], "handoff_whatsapp")
        self.assertIn("wa.me/491701234567", data["wa_me_url"])
        self.assertIn("Bok%20Wolfgang", data["wa_me_url"])

    @patch.dict(os.environ, {}, clear=False)
    def test_send_whatsapp_handoff_long_body(self):
        """Regression: long check-in text must not 500 (wa_me_url was varchar 512)."""
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        compose = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        draft_id = compose.json()["draft_id"]
        body = (
            "Molimo vas da nam pošaljete potrebne dokumente. "
            "Šibenik check-in u 15:00. "
        ) * 80

        response = self.client.post(
            f"{self.base}/send/",
            {
                "draft_id": draft_id,
                "channel": "whatsapp",
                "body_text": body,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["status"], "handoff_whatsapp")
        self.assertIn("wa.me/491701234567", data["wa_me_url"])
        self.assertGreater(len(data["wa_me_url"]), 512)

    def test_send_whatsapp_no_phone(self):
        self.reservation.booker_phone = ""
        self.reservation.save(update_fields=["booker_phone"])
        compose = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        draft_id = compose.json()["draft_id"]
        response = self.client.post(
            f"{self.base}/send/",
            {
                "draft_id": draft_id,
                "channel": "whatsapp",
                "body_text": "Test",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_compose_requires_write_scope(self):
        read_app, read_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Read only",
            scopes=["reception:read"],
        )
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {read_token}",
        )
        self.assertEqual(response.status_code, 403)
        read_app.delete()

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_includes_booking_channel_for_channex_reservation(self):
        from apps.integrations.channex.booking_service import channex_external_id
        from apps.integrations.models import IntegrationConfig
        from apps.tenants.models import ChannelManager, TenantReceptionSettings

        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.reservation.import_source = "channex"
        self.reservation.external_id = channex_external_id("test-booking-uuid")
        self.reservation.save(update_fields=["import_source", "external_id"])

        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["channels"]["booking"]["available"])

    @patch("apps.communications.guest_message_send.send_message_for_reservation")
    @patch.dict(os.environ, {}, clear=False)
    def test_send_booking_channel(self, mock_send):
        from apps.integrations.channex.booking_service import channex_external_id
        from apps.integrations.models import ChannexMessage, IntegrationConfig
        from apps.tenants.models import ChannelManager, TenantReceptionSettings

        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.reservation.import_source = "channex"
        self.reservation.external_id = channex_external_id("test-booking-uuid")
        self.reservation.save(update_fields=["import_source", "external_id"])

        mock_send.return_value = ChannexMessage.objects.create(
            tenant=self.tenant,
            channex_booking_id="test-booking-uuid",
            channex_message_id="msg-out-1",
            direction=ChannexMessage.Direction.OUTBOUND,
            sender=ChannexMessage.Sender.PROPERTY,
            body="Reply via Booking.com",
            reservation=self.reservation,
        )

        compose = self.client.post(
            f"{self.base}/compose/",
            {"intent": "reply"},
            format="json",
            **self.auth,
        )
        draft_id = compose.json()["draft_id"]
        body = "Reply via Booking.com"

        response = self.client.post(
            f"{self.base}/send/",
            {
                "draft_id": draft_id,
                "channel": "booking",
                "body_text": body,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["channel"], "booking")
        self.assertEqual(data["source"], "booking")
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["body_text"], body)
        mock_send.assert_called_once()

        timeline = self.client.get(f"{self.base}/", **self.auth)
        self.assertEqual(len(timeline.json()), 1)
        self.assertEqual(timeline.json()[0]["source"], "booking")

    def test_timeline_includes_channex_inbound(self):
        from apps.integrations.models import ChannexMessage

        ChannexMessage.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            channex_booking_id="booking-1",
            channex_message_id="msg-in-1",
            direction=ChannexMessage.Direction.INBOUND,
            sender=ChannexMessage.Sender.GUEST,
            body="Hello from guest",
        )

        response = self.client.get(f"{self.base}/", **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["source"], "booking")
        self.assertEqual(data[0]["direction"], "inbound")
        self.assertEqual(data[0]["body_text"], "Hello from guest")

    @patch("apps.integrations.channex.message_service.ChannexClient")
    def test_timeline_syncs_channex_when_empty(self, mock_client_cls):
        from unittest.mock import MagicMock

        from apps.integrations.channex.booking_service import channex_external_id
        from apps.integrations.models import IntegrationConfig
        from apps.tenants.models import ChannelManager, TenantReceptionSettings

        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.reservation.import_source = "channex"
        booking_id = "timeline-booking-uuid"
        self.reservation.external_id = channex_external_id(booking_id)
        self.reservation.save(update_fields=["import_source", "external_id"])

        mock_client = MagicMock()
        mock_client.list_booking_messages.return_value = {
            "data": [
                {
                    "id": "remote-timeline-msg",
                    "attributes": {
                        "message": "Guest reply from Booking.com",
                        "sender": "guest",
                        "booking_id": booking_id,
                        "inserted_at": "2026-05-27T08:10:00.000000",
                    },
                }
            ]
        }
        mock_client_cls.return_value = mock_client

        response = self.client.get(f"{self.base}/", **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["source"], "booking")
        self.assertEqual(data[0]["direction"], "inbound")
        self.assertEqual(data[0]["body_text"], "Guest reply from Booking.com")

    @patch.dict(os.environ, {}, clear=False)
    def test_compose_direct_platform_has_email_not_booking(self):
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        self.reservation.source = "api"
        self.reservation.import_source = ""
        self.reservation.external_id = "WEB-123"
        self.reservation.save(update_fields=["source", "import_source", "external_id"])

        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["channels"]["email"]["available"])
        self.assertFalse(data["channels"]["booking"]["available"])
        self.assertTrue(data["channels"]["whatsapp"]["available"])
