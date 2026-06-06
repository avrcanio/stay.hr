from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.communications.guest_message_timeline import WA_ID_OFFSET
from apps.communications.models import GuestMessageTranslation
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class GuestMessageTranslateTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Uzorita",
            slug="uzorita",
            default_language="hr",
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Luxury Room Uzorita",
            slug="uzorita",
            timezone="Europe/Zagreb",
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
            check_in=timezone.localdate(),
            check_out=timezone.localdate(),
            status=Reservation.Status.EXPECTED,
            booker_name="Christine Hartwig",
            booker_email="christine@example.com",
            booker_phone="+49 170 1234567",
            amount=Decimal("180.15"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="Luxury Room Uzorita - R3",
            sort_order=0,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Christine",
            last_name="Hartwig",
            email="christine@example.com",
            is_primary=True,
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            is_active=True,
            config={"phone_number_id": "123"},
        )
        self.wa_message = WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.inbound.test",
            wa_id="491701234567",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="Wir freuen uns",
        )
        self.timeline_id = WA_ID_OFFSET + self.wa_message.pk
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}
        self.url = (
            f"/api/v1/reception/reservations/{self.reservation.pk}/messages/translate/"
        )

    @patch("apps.communications.guest_message_translate.translation_available", return_value=True)
    @patch("apps.communications.guest_message_translate.translate_text")
    def test_translate_caches_on_server(self, mock_translate, _mock_available):
        mock_translate.return_value = "Radujemo se"

        first = self.client.post(
            self.url,
            {"timeline_id": self.timeline_id, "lang": "hr"},
            format="json",
            **self.auth,
        )
        self.assertEqual(first.status_code, 200)
        data = first.json()
        self.assertEqual(data["translated"], "Radujemo se")
        self.assertTrue(data["is_translated"])
        self.assertFalse(data["from_cache"])
        mock_translate.assert_called_once()

        mock_translate.reset_mock()
        second = self.client.post(
            self.url,
            {"timeline_id": self.timeline_id, "lang": "hr"},
            format="json",
            **self.auth,
        )
        self.assertEqual(second.status_code, 200)
        second_data = second.json()
        self.assertEqual(second_data["translated"], "Radujemo se")
        self.assertTrue(second_data["from_cache"])
        mock_translate.assert_not_called()

        self.assertEqual(
            GuestMessageTranslation.objects.filter(
                tenant=self.tenant,
                message_source="whatsapp",
                source_id=self.wa_message.pk,
                target_lang="hr",
            ).count(),
            1,
        )

    @patch("apps.communications.guest_message_translate.translation_available", return_value=True)
    @patch("apps.communications.guest_message_translate.translate_text")
    def test_translate_different_lang_new_cache_entry(self, mock_translate, _mock_available):
        mock_translate.side_effect = ["Radujemo se", "We are looking forward"]

        self.client.post(
            self.url,
            {"timeline_id": self.timeline_id, "lang": "hr"},
            format="json",
            **self.auth,
        )
        mock_translate.reset_mock()
        mock_translate.return_value = "We are looking forward"

        response = self.client.post(
            self.url,
            {"timeline_id": self.timeline_id, "lang": "en"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target_lang"], "en")
        mock_translate.assert_called_once()
        self.assertEqual(GuestMessageTranslation.objects.filter(tenant=self.tenant).count(), 2)

    def test_translate_unknown_timeline_id(self):
        response = self.client.post(
            self.url,
            {"timeline_id": 999999, "lang": "hr"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
