from django.test import TestCase

from apps.integrations.evisitor.messages import (
    format_evisitor_user_message,
    parse_existing_registration_id,
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
