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
        self.assertTrue(data["channels"]["email"]["available"])
        self.assertEqual(data["channels"]["email"]["to"], "wolfgang@example.com")
        self.assertTrue(data["channels"]["whatsapp"]["available"])
        self.assertIn("491701234567", data["channels"]["whatsapp"]["phone_wa"])

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
            {"intent": "checkin"},
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
