from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.communications.guest_email_ingest import (
    extract_booking_code,
    extract_guest_body_text,
    ingest_parsed_email,
    parse_guest_email_bytes,
    poll_tenant_guest_inbox,
)
from apps.communications.models import GuestInboundMessage
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant, TenantReceptionSettings

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_EML = FIXTURES / "booking_guest_reply_pierre.eml"


class GuestEmailIngestParseTests(TestCase):
    def setUp(self):
        self.raw = SAMPLE_EML.read_bytes()

    def test_parse_sample_eml_booking_code_and_guest_text(self):
        parsed = parse_guest_email_bytes(self.raw)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.booking_code, "5238895494")
        self.assertEqual(parsed.body_text, "Ok merci du mail")
        self.assertTrue(parsed.message_id)
        self.assertIn("@guest.booking.com", parsed.raw_from.lower())

    def test_extract_booking_code_from_body(self):
        parsed = parse_guest_email_bytes(self.raw)
        assert parsed is not None
        self.assertEqual(parsed.booking_code, "5238895494")
        self.assertEqual(
            extract_booking_code(
                body_text="Confirmation number: 5238895494",
                subject="",
            ),
            "5238895494",
        )

    def test_skip_own_outbound_mail(self):
        own_mail = (
            b"From: room_reservations@uzorita.hr\r\n"
            b"To: guest@example.com\r\n"
            b"Subject: Outbound copy\r\n"
            b"Message-ID: <own-copy-1@test>\r\n"
            b"\r\n"
            b"Confirmation number: 5238895494\r\n"
            b"Guest said:\r\nHello\r\n"
        )
        parsed = parse_guest_email_bytes(own_mail)
        self.assertIsNone(parsed)


class GuestEmailIngestIngestTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            guest_contact_email="room_reservations@uzorita.hr",
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="5238895494",
            check_in=timezone.localdate(),
            check_out=timezone.localdate(),
            booker_name="Pierre Test",
        )
        self.raw = SAMPLE_EML.read_bytes()
        self.parsed = parse_guest_email_bytes(self.raw)
        assert self.parsed is not None

    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    def test_ingest_creates_inbound_row_and_notifies(self, mock_notify):
        row = ingest_parsed_email(self.tenant, self.parsed, notify=True)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.channel, "email")
        self.assertEqual(row.reservation_id, self.reservation.pk)
        self.assertEqual(row.message_id, self.parsed.message_id)
        mock_notify.assert_called_once()

    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    def test_dedup_message_id(self, mock_notify):
        ingest_parsed_email(self.tenant, self.parsed, notify=True)
        second = ingest_parsed_email(self.tenant, self.parsed, notify=True)
        self.assertIsNone(second)
        self.assertEqual(GuestInboundMessage.objects.count(), 1)
        mock_notify.assert_called_once()

    @patch("apps.communications.guest_email_ingest._connect_imap")
    def test_poll_skips_when_imap_disabled(self, mock_connect):
        settings = self.tenant.reception_settings
        settings.guest_imap_enabled = False
        settings.save(update_fields=["guest_imap_enabled"])
        result = poll_tenant_guest_inbox(self.tenant)
        self.assertEqual(result.ingested, 0)
        mock_connect.assert_not_called()
