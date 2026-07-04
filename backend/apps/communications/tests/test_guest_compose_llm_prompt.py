import json

from django.test import TestCase

from apps.communications.guest_compose import (
    _compose_context_for_llm,
    _user_prompt,
)
from apps.communications.guest_language_context import (
    GuestLanguageContext,
    LanguageMode,
    LanguageSource,
)
from apps.communications.models import GuestMessageIntent


class GuestComposeLlmPromptTests(TestCase):
    def test_compose_context_for_llm_serializes_language_context(self):
        ctx = GuestLanguageContext(
            language="en",
            source=LanguageSource.MESSAGE,
            confidence=0.9,
            mode=LanguageMode.REACTIVE,
            reason="inbound text",
        )
        payload = _compose_context_for_llm(
            {
                "language": "en",
                "language_context": ctx,
                "guest_name": "Test Guest",
            }
        )
        json.dumps(payload)
        self.assertEqual(payload["language_context"]["source"], "message")
        self.assertEqual(payload["language_context"]["mode"], "reactive")

    def test_user_prompt_is_json_serializable(self):
        ctx = GuestLanguageContext(
            language="hr",
            source=LanguageSource.COUNTRY,
            confidence=1.0,
            mode=LanguageMode.REACTIVE,
            reason="booker_country",
        )
        prompt = _user_prompt(
            GuestMessageIntent.REPLY,
            "",
            {
                "language": "hr",
                "language_context": ctx,
                "guest_name": "Ana",
                "message_history": [],
            },
        )
        self.assertIn("Task:", prompt)
        self.assertIn("booker_country", prompt)
