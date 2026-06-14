"""Tests for complete_chat_json."""

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.ai.provider import GuestComposeError, complete_chat_json


class CompleteChatJsonTests(TestCase):
    @patch("apps.ai.provider._post_chat_completion")
    def test_parses_json_object(self, mock_post):
        mock_post.return_value = {
            "choices": [{"message": {"content": json.dumps({"ok": True, "value": 1})}}],
        }
        result = complete_chat_json("system", "user")
        self.assertEqual(result, {"ok": True, "value": 1})

    @patch("apps.ai.provider._post_chat_completion")
    def test_invalid_json_raises(self, mock_post):
        mock_post.return_value = {
            "choices": [{"message": {"content": "not json"}}],
        }
        with self.assertRaises(GuestComposeError):
            complete_chat_json("system", "user")

    @patch("apps.ai.provider._post_chat_completion")
    def test_non_object_json_raises(self, mock_post):
        mock_post.return_value = {
            "choices": [{"message": {"content": "[1,2]"}}],
        }
        with self.assertRaises(GuestComposeError):
            complete_chat_json("system", "user")
