from django.test import SimpleTestCase

from apps.communications.guest_compose import FOOTER
from apps.communications.guest_email_html import (
    prepare_guest_email_bodies,
    render_guest_message_email_html,
)
from apps.communications.guest_message_body_format import normalize_outbound_plain_text


class GuestEmailHtmlTests(SimpleTestCase):
    def test_single_line_llm_text_gets_paragraphs(self):
        raw = (
            "Poštovani gospodine Vrcan, Vaša rezervacija u Uzorita B&B je potvrđena! "
            "Imate besplatnu sobu, stoga slobodno dođite kad želite. "
            "Radujemo se vašem dolasku!"
        )
        plain, html_part = prepare_guest_email_bodies(raw)
        self.assertGreater(plain.count("\n"), 0)
        self.assertIn("<p>", html_part)
        self.assertGreater(html_part.count("<p>"), 1)

    def test_checkin_fallback_bullets_use_br(self):
        raw = "\n".join(
            [
                "Poštovani Wolfgang,",
                "",
                "Hvala na rezervaciji.",
                "",
                "Rezervacija:",
                "• BCOM-100",
                "• Uzorita",
                f"• Deluxe Room",
                "",
                FOOTER,
            ]
        )
        html_part = render_guest_message_email_html(raw)
        self.assertIn("• BCOM-100", html_part)
        self.assertIn("<br>", html_part)
        self.assertIn("#666", html_part)

    def test_escapes_html_in_body(self):
        raw = "Hello <script>alert(1)</script> & welcome"
        html_part = render_guest_message_email_html(raw)
        self.assertNotIn("<script>", html_part)
        self.assertIn("&lt;script&gt;", html_part)
        self.assertIn("&amp;", html_part)

    def test_explicit_body_html_not_overwritten(self):
        custom_html = "<p>Custom HTML only</p>"
        plain, html_part = prepare_guest_email_bodies("Plain text", body_html=custom_html)
        self.assertEqual(html_part, custom_html)
        self.assertEqual(plain, normalize_outbound_plain_text("Plain text"))

    def test_normalize_outbound_preserves_existing_newlines(self):
        raw = "Line one\n\nLine two"
        self.assertEqual(normalize_outbound_plain_text(raw), "Line one\n\nLine two")
