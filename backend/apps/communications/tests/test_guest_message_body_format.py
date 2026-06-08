from django.test import SimpleTestCase

from apps.communications.guest_message_body_format import (
    format_timeline_body_text,
    strip_booking_email_boilerplate,
    timeline_body_quality_score,
)


class GuestMessageBodyFormatTests(SimpleTestCase):
    def test_strip_booking_boilerplate(self):
        raw = (
            "##- Please type your reply above this line -##\n"
            "The accommodation provider takes full responsibility for the content of this message, sent through Booking.com\n"
            "Poštovani gospodine Vrcan,\n\n"
            "Vaša rezervacija je potvrđena.\n\n"
            "Uzorita B&B\n"
            "*Booking.com will receive and process replies to this email as set forth in the Booking.com Privacy Statement."
        )
        cleaned = strip_booking_email_boilerplate(raw)
        self.assertIn("Poštovani gospodine Vrcan", cleaned)
        self.assertIn("Vaša rezervacija je potvrđena", cleaned)
        self.assertNotIn("accommodation provider takes full responsibility", cleaned.lower())
        self.assertNotIn("Booking.com will receive", cleaned)

    def test_reflow_single_line_checkin(self):
        raw = (
            "The accommodation provider takes full responsibility for the content of this message, sent through Booking.com "
            "Poštovani gospodine Vrcan, Vaša rezervacija u Uzorita B&B je potvrđena! Imate besplatnu sobu, stoga slobodno dođite kad želite. "
            "Radujemo se vašem dolasku! Uzorita B&B Managed by stay.hr — https://stay.hr/ "
            "*Booking.com will receive and process replies to this email as set forth in the Booking.com Privacy Statement."
        )
        formatted = format_timeline_body_text(raw)
        self.assertIn("Poštovani gospodine Vrcan,", formatted)
        self.assertGreater(formatted.count("\n"), 1)
        self.assertNotIn("accommodation provider", formatted.lower())

    def test_quality_prefers_structured_body(self):
        bloated = (
            "The accommodation provider takes full responsibility for the content of this message, sent through Booking.com "
            "Poštovani, " + ("duga poruka bez prijeloma. " * 20)
        )
        structured = "Poštovani,\n\nKratka poruka.\n\nLijep pozdrav,"
        self.assertGreater(
            timeline_body_quality_score(structured),
            timeline_body_quality_score(bloated),
        )

    def test_html_breaks_to_newlines(self):
        raw = "<p>Pozdrav,</p><p>hvala na poruci.</p>"
        formatted = format_timeline_body_text(raw)
        self.assertIn("Pozdrav,", formatted)
        self.assertIn("hvala na poruci.", formatted)
        self.assertGreater(formatted.count("\n"), 0)
