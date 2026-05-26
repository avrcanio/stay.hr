from django.test import TestCase

from apps.integrations.evisitor.messages import (
    format_evisitor_user_message,
    parse_existing_registration_id,
    resolve_evisitor_error_message,
)

SAMPLE = (
    "[[[Osoba %0 %1 je već prijavljena na datum %2 te nije odjavljena. "
    "ID postojeće prijave: %3|||Lauriane|||Saulnier|||20.5.2026.|||"
    "a01c2e9f-3839-4f0e-b39b-775e107d6f36]]]"
)


class EvisitorMessagesTests(TestCase):
    def test_format_already_registered(self):
        msg = format_evisitor_user_message(SAMPLE)
        self.assertIn("Lauriane", msg)
        self.assertIn("Saulnier", msg)
        self.assertIn("a01c2e9f-3839-4f0e-b39b-775e107d6f36", msg)
        self.assertIn("već prijavljena", msg)

    def test_parse_existing_registration_id(self):
        reg_id = parse_existing_registration_id(SAMPLE)
        self.assertEqual(reg_id, "a01c2e9f-3839-4f0e-b39b-775e107d6f36")

    def test_parse_returns_none_for_other_errors(self):
        self.assertIsNone(parse_existing_registration_id("Nepoznata greška"))

    def test_resolve_from_system_message_json(self):
        system = (
            '{"UserMessage":"[[[Zadana kategorija BP nije dozvoljena '
            'za osobe mla\\u0111e od 18 godina.]]]","SystemMessage":null}'
        )
        msg = resolve_evisitor_error_message(
            user_message="eVisitor CheckInTourist HTTP 400",
            system_message=system,
            fallback="eVisitor CheckInTourist HTTP 400",
        )
        self.assertEqual(
            msg,
            "Zadana kategorija BP nije dozvoljena za osobe mlađe od 18 godina.",
        )

    def test_resolve_prefers_user_message_when_readable(self):
        msg = resolve_evisitor_error_message(
            user_message="[[[Test greška.]]]",
            system_message='{"UserMessage":"[[[Druga greška.]]]"}',
            fallback="fallback",
        )
        self.assertEqual(msg, "Test greška.")
