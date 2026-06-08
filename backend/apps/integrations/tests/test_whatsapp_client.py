from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.integrations.whatsapp.client import WhatsAppApiError, send_template_message, send_text_message


class WhatsAppClientTests(SimpleTestCase):
    @patch("apps.integrations.whatsapp.client.httpx.post")
    def test_send_text_message_meta(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.meta"}]}
        mock_post.return_value = mock_response

        data = send_text_message(
            phone_number_id="123456",
            access_token="meta-token",
            to_wa_id="385976789626",
            body="Hello Meta",
            provider="meta",
        )

        self.assertEqual(data["messages"][0]["id"], "wamid.meta")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(
            args[0],
            "https://graph.facebook.com/v23.0/123456/messages",
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer meta-token")

    @override_settings()
    @patch.dict(
        "os.environ",
        {
            "D360_API_KEY": "d360-key",
            "D360_API_BASE_URL": "https://waba-v2.360dialog.io",
        },
    )
    @patch("apps.integrations.whatsapp.client.httpx.post")
    def test_send_text_message_360dialog(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.d360"}]}
        mock_post.return_value = mock_response

        data = send_text_message(
            phone_number_id="",
            access_token="d360-key",
            to_wa_id="385976789626",
            body="Hello 360dialog",
            provider="360dialog",
        )

        self.assertEqual(data["messages"][0]["id"], "wamid.d360")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://waba-v2.360dialog.io/messages")
        self.assertEqual(kwargs["headers"]["D360-API-KEY"], "d360-key")
        self.assertNotIn("Authorization", kwargs["headers"])

    @patch.dict("os.environ", {}, clear=True)
    def test_send_text_message_360dialog_missing_key(self):
        with self.assertRaises(WhatsAppApiError):
            send_text_message(
                phone_number_id="",
                access_token="",
                to_wa_id="385976789626",
                body="Hello",
                provider="360dialog",
            )

    @override_settings()
    @patch.dict(
        "os.environ",
        {
            "D360_API_KEY": "d360-key",
            "D360_API_BASE_URL": "https://waba-v2.360dialog.io",
        },
    )
    @patch("apps.integrations.whatsapp.client.httpx.post")
    def test_send_template_message_360dialog(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.template"}]}
        mock_post.return_value = mock_response

        data = send_template_message(
            phone_number_id="",
            access_token="d360-key",
            to_wa_id="385976789626",
            template_name="stay_welcome_hr",
            language_code="hr",
            body_parameters=["Ana", "BCOM-1", "Uzorita", "2026-06-07", "2026-06-09"],
            header_image_url="https://stay.hr/static/whatsapp-header.png",
            provider="360dialog",
        )

        self.assertEqual(data["messages"][0]["id"], "wamid.template")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["type"], "template")
        self.assertEqual(payload["template"]["name"], "stay_welcome_hr")
        self.assertEqual(len(payload["template"]["components"]), 2)
