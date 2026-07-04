from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.integrations.whatsapp.media_download import fetch_whatsapp_media


class WhatsAppMediaDownloadTests(SimpleTestCase):
    @patch("apps.integrations.whatsapp.media_download.httpx.get")
    def test_fetch_whatsapp_media_meta(self, mock_get):
        meta_response = MagicMock()
        meta_response.status_code = 200
        meta_response.json.return_value = {
            "url": "https://lookaside.fbsbx.com/media.bin",
            "mime_type": "image/jpeg",
        }
        file_response = MagicMock()
        file_response.status_code = 200
        file_response.content = b"image-bytes"
        mock_get.side_effect = [meta_response, file_response]

        content, mime = fetch_whatsapp_media(
            media_id="media-123",
            access_token="meta-token",
        )

        self.assertEqual(content, b"image-bytes")
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(mock_get.call_count, 2)
        self.assertIn("Bearer meta-token", mock_get.call_args_list[0].kwargs["headers"]["Authorization"])
