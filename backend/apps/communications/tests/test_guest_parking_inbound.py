from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.communications.guest_parking_inbound import maybe_handle_guest_parking_inbound
from apps.communications.guest_parking_patterns import classify_parking_only
from apps.communications.models import GuestMessageDraft
from apps.properties.guest_info import (
    merge_parking_into_guest_info,
    normalize_guest_info,
    render_parking_reply_text,
)
from apps.properties.models import Property
from apps.properties.uzorita_guest_info import UZORITA_GUEST_INFO
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class GuestParkingPatternTests(TestCase):
    def test_parking_only(self):
        self.assertTrue(classify_parking_only("Gdje je parking?"))
        self.assertFalse(classify_parking_only("We arrive at 8 PM"))

    def test_mixed_deferred_to_arrival(self):
        self.assertFalse(
            classify_parking_only("We need parking and arrive at 8 PM"),
        )


class GuestParkingInboundTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="parking", name="Parking")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Test",
            slug="test",
            guest_info=merge_parking_into_guest_info(
                {},
                has_private=True,
                zone_label="Zone B",
                price_per_day=Decimal("0"),
                custom_hr="Ispred objekta.",
                custom_en="In front of the property.",
            ),
            guest_parking_auto_reply_enabled=True,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 8, 4),
            check_out=date(2026, 8, 5),
            status=Reservation.Status.EXPECTED,
            booker_name="Olga Test",
        )

    @patch("apps.communications.guest_parking_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_parking_inbound.send_guest_message")
    def test_parking_auto_reply_booking_channel(self, mock_send, _mock_llm):
        result = maybe_handle_guest_parking_inbound(
            self.reservation,
            "Do you have free parking?",
            channel="booking",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "guest_parking_handled")
        mock_send.assert_called_once()
        draft = GuestMessageDraft.objects.filter(reservation=self.reservation).first()
        self.assertIsNotNone(draft)
        self.assertIn("parking", draft.final_body_text.lower())

    @patch("apps.communications.guest_parking_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_parking_inbound.send_guest_message")
    def test_toggle_off_skips(self, mock_send, _mock_llm):
        self.property.guest_parking_auto_reply_enabled = False
        self.property.save(update_fields=["guest_parking_auto_reply_enabled", "updated_at"])
        result = maybe_handle_guest_parking_inbound(
            self.reservation,
            "Parking?",
            channel="email",
        )
        self.assertIsNone(result)
        mock_send.assert_not_called()

    @patch("apps.communications.guest_parking_inbound.llm_configured", return_value=False)
    @patch("apps.communications.guest_parking_inbound.send_guest_message")
    def test_dedup_same_day(self, mock_send, _mock_llm):
        maybe_handle_guest_parking_inbound(
            self.reservation,
            "Where is parking?",
            channel="email",
        )
        result = maybe_handle_guest_parking_inbound(
            self.reservation,
            "Parking again?",
            channel="email",
        )
        self.assertEqual(result["reply"]["status"], "dedup_skipped")
        self.assertEqual(mock_send.call_count, 1)


class GuestInfoParkingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="pinfo", name="Pinfo")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="pinfo",
            name="Pinfo",
        )

    def test_normalize_uzorita_parking_facts(self):
        normalized = normalize_guest_info(UZORITA_GUEST_INFO)
        parking = normalized["facts"]["parking"]
        self.assertTrue(parking.get("has_private"))
        self.assertEqual(parking.get("price_per_day"), "0")

    def test_render_free_parking_en(self):
        self.property.guest_info = merge_parking_into_guest_info(
            {},
            has_private=True,
            zone_label="City center",
            price_per_day=Decimal("0"),
            custom_en="Park in front of the restaurant.",
        )
        text = render_parking_reply_text(self.property, "en")
        self.assertIn("free", text.lower())
        self.assertIn("City center", text)

    def test_render_priced_parking_hr(self):
        self.property.guest_info = merge_parking_into_guest_info(
            {},
            zone_label="Zona A",
            price_per_day=Decimal("5.00"),
            currency="EUR",
        )
        text = render_parking_reply_text(self.property, "hr")
        self.assertIn("5.00", text)
        self.assertIn("EUR", text)

    def test_reservation_notes_prefix(self):
        self.property.guest_info = merge_parking_into_guest_info(
            {},
            price_per_day=Decimal("0"),
        )
        text = render_parking_reply_text(
            self.property,
            "en",
            reservation_notes="Guest would like free parking",
        )
        self.assertTrue(text.startswith("We see you requested parking"))
