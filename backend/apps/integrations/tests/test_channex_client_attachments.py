from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations.channex.client import ChannexClient
from apps.integrations.channex.config import ChannexRuntimeConfig


class ChannexClientAttachmentTests(TestCase):
    def _client(self) -> ChannexClient:
        config = ChannexRuntimeConfig(
            environment="staging",
            base_url="https://staging.channex.io/api/v1",
            property_id="prop-1",
            api_key="test-key",
        )
        return ChannexClient(config)

    @patch("httpx.Client.request")
    def test_get_availability_returns_data_object(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        payload = {
            "data": {
                "rt-1": {"2026-08-01": 1, "2026-08-02": 0},
            }
        }
        mock_response.content = b'{"data":{}}'
        mock_response.json.return_value = payload
        mock_request.return_value = mock_response

        client = self._client()
        try:
            data = client.get_availability(
                property_id="prop-1",
                date_from="2026-08-01",
                date_to="2026-08-02",
            )
        finally:
            client.close()

        self.assertEqual(data["rt-1"]["2026-08-01"], 1)
        _args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["params"]["filter[property_id]"], "prop-1")
        self.assertEqual(kwargs["params"]["filter[date][gte]"], "2026-08-01")
        self.assertEqual(kwargs["params"]["filter[date][lte]"], "2026-08-02")

    @patch("httpx.Client.request")
    def test_upload_attachment_returns_id(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data":{"id":"attach-1","type":"attachment"}}'
        mock_response.json.return_value = {"data": {"id": "attach-1", "type": "attachment"}}
        mock_request.return_value = mock_response

        client = self._client()
        try:
            attachment_id = client.upload_attachment(
                file_bytes=b"fake-image",
                file_name="photo.jpg",
                file_type="image/jpeg",
            )
        finally:
            client.close()

        self.assertEqual(attachment_id, "attach-1")
        _args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["attachment"]["file_name"], "photo.jpg")

    @patch("httpx.Client.request")
    def test_send_booking_message_with_attachment_id(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data":{"id":"msg-1"}}'
        mock_response.json.return_value = {"data": {"id": "msg-1"}}
        mock_request.return_value = mock_response

        client = self._client()
        try:
            client.send_booking_message(
                "booking-uuid",
                "Caption text",
                attachment_id="attach-1",
            )
        finally:
            client.close()

        _args, kwargs = mock_request.call_args
        self.assertEqual(
            kwargs["json"],
            {"message": {"attachment_id": "attach-1", "message": "Caption text"}},
        )
