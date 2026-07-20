import uuid
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.billing.exceptions import FiscalizationError
from apps.billing.services.fiskal_platform.client import FiskalExecutionClient


class FiskalExecutionClientTests(SimpleTestCase):
    def _response(self, *, status_code: int, json_data=None, text: str = ""):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = text
        response.raise_for_status.side_effect = None
        if status_code >= 400:
            import httpx

            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error",
                request=MagicMock(),
                response=response,
            )
        return response

    @override_settings(
        FISKAL_PLATFORM_URL="http://fiskal-api:8000",
        FISKAL_PLATFORM_API_KEY="test-key",
        FISKAL_EXECUTION_POLL_INTERVAL=0.01,
        FISKAL_EXECUTION_POLL_TIMEOUT=0.05,
    )
    def test_submit_execution_returns_request_id(self):
        request_id = uuid.uuid4()
        mock_client = MagicMock()
        mock_client.post.return_value = self._response(
            status_code=202,
            json_data={
                "request_id": str(request_id),
                "correlation_id": "corr-1",
                "status": "received",
            },
        )

        client = FiskalExecutionClient(http_client=mock_client)
        result = client.submit_execution({"operation": "fiscalize"}, idempotency_key="stay-1")

        self.assertEqual(result.request_id, request_id)
        self.assertEqual(result.status, "received")
        mock_client.post.assert_called_once()
        _, kwargs = mock_client.post.call_args
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "stay-1")
        self.assertIn("X-Correlation-ID", kwargs["headers"])

    @override_settings(
        FISKAL_PLATFORM_URL="http://fiskal-api:8000",
        FISKAL_PLATFORM_API_KEY="test-key",
    )
    def test_get_execution_maps_status(self):
        request_id = uuid.uuid4()
        mock_client = MagicMock()
        mock_client.get.return_value = self._response(
            status_code=200,
            json_data={
                "id": str(request_id),
                "status": "ACCEPTED",
                "jir": "ABC-DEF-123",
                "zki": "zki123",
            },
        )

        client = FiskalExecutionClient(http_client=mock_client)
        status = client.get_execution(request_id)

        self.assertEqual(status.request_id, request_id)
        self.assertEqual(status.status, "accepted")
        self.assertEqual(status.jir, "ABC-DEF-123")

    @override_settings(
        FISKAL_PLATFORM_URL="http://fiskal-api:8000",
        FISKAL_PLATFORM_API_KEY="test-key",
        FISKAL_EXECUTION_POLL_INTERVAL=0.01,
        FISKAL_EXECUTION_POLL_TIMEOUT=0.2,
    )
    def test_poll_until_terminal_accepts(self):
        request_id = uuid.uuid4()
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            self._response(status_code=200, json_data={"id": str(request_id), "status": "sent"}),
            self._response(
                status_code=200,
                json_data={
                    "id": str(request_id),
                    "status": "accepted",
                    "jir": "ABC-DEF-123",
                },
            ),
        ]

        client = FiskalExecutionClient(http_client=mock_client)
        status = client.poll_until_terminal(request_id)

        self.assertEqual(status.status, "accepted")
        self.assertEqual(status.jir, "ABC-DEF-123")

    @override_settings(
        FISKAL_PLATFORM_URL="http://fiskal-api:8000",
        FISKAL_PLATFORM_API_KEY="test-key",
    )
    def test_submit_maps_401_to_fiscalization_error(self):
        mock_client = MagicMock()
        mock_client.post.return_value = self._response(
            status_code=401,
            json_data={"error_code": "FP-0101", "message": "Unauthorized"},
        )

        client = FiskalExecutionClient(http_client=mock_client)
        with self.assertRaises(FiscalizationError) as ctx:
            client.submit_execution({"operation": "fiscalize"})
        self.assertIn("FP-0101", str(ctx.exception))
