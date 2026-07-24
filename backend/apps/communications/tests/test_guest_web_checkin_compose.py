from datetime import date
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase

from apps.communications.guest_compose import (
    append_guest_checkin_lang,
    render_autocheckin_web_checkin_message,
    render_channex_guest_checkin_link_message,
    render_guest_web_checkin_reminder_message,
)
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class AppendGuestCheckinLangTests(TestCase):
    def test_appends_lang_query(self):
        url = append_guest_checkin_lang("https://booking.uzorita.hr/check-in/tok", "de")
        self.assertEqual(url, "https://booking.uzorita.hr/check-in/tok?lang=de")

    def test_replaces_existing_lang(self):
        url = append_guest_checkin_lang(
            "https://booking.uzorita.hr/check-in/tok?lang=hr&x=1",
            "en",
        )
        parts = urlsplit(url)
        qs = parse_qs(parts.query)
        self.assertEqual(qs["lang"], ["en"])
        self.assertEqual(qs["x"], ["1"])

    def test_ignores_invalid_lang(self):
        base = "https://booking.uzorita.hr/check-in/tok"
        self.assertEqual(append_guest_checkin_lang(base, "not-a-lang"), base)
        self.assertEqual(append_guest_checkin_lang(base, ""), base)
        self.assertEqual(append_guest_checkin_lang(base, None), base)


class AutocheckinWebCheckinComposeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo-web-ci", name="Demo", default_language="en")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Demo Property",
            slug="demo",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ada Lovelace",
            booker_phone="+385911111111",
            booker_country="GB",
            check_in=date(2026, 8, 1),
            check_out=date(2026, 8, 3),
            status=Reservation.Status.EXPECTED,
            adults_count=2,
        )
        self.checkin_url = "https://booking.example.test/check-in/abc123"

    def test_web_checkin_message_omits_whatsapp_docs_sentence_and_has_lang(self):
        text = render_autocheckin_web_checkin_message(
            self.reservation,
            checkin_url=self.checkin_url,
        )
        self.assertNotIn("ne prima slike", text.lower())
        self.assertNotIn("no longer accepts", text.lower())
        self.assertIn("?lang=", text)
        self.assertIn(f"{self.checkin_url}?lang=", text)

    def test_reminder_and_channex_include_lang(self):
        reminder = render_guest_web_checkin_reminder_message(
            self.reservation,
            checkin_url=self.checkin_url,
        )
        channex = render_channex_guest_checkin_link_message(
            self.reservation,
            checkin_url=self.checkin_url,
        )
        self.assertIn(f"{self.checkin_url}?lang=", reminder)
        self.assertIn(f"{self.checkin_url}?lang=", channex)
