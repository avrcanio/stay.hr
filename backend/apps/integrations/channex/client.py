from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexApiError

logger = logging.getLogger(__name__)


class ChannexClient:
    def __init__(self, config: ChannexRuntimeConfig) -> None:
        self._config = config
        self._session = httpx.Client(
            timeout=30.0,
            headers={
                "user-api-key": config.api_key,
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> ChannexClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return f"{self._config.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._session.request(method, self._url(path), **kwargs)
        except httpx.HTTPError as exc:
            raise ChannexApiError(f"Channex HTTP error: {exc}") from exc

        if response.status_code >= 400:
            body = response.text[:500]
            raise ChannexApiError(
                f"Channex {method} {path} failed ({response.status_code}): {body}"
            )

        if not response.content:
            return {}
        data = response.json()
        if not isinstance(data, dict):
            raise ChannexApiError(f"Unexpected Channex response type for {path}")
        return data

    def get_booking_revision(self, revision_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/booking_revisions/{revision_id}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ChannexApiError(f"Booking revision {revision_id} not found in response")
        return data

    def get_booking(self, booking_id: str) -> dict[str, Any]:
        """Fetch latest booking revision details by Channex booking UUID."""
        payload = self._request("GET", f"/bookings/{booking_id}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ChannexApiError(f"Booking {booking_id} not found in response")
        return data

    def list_bookings(self, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", "/bookings", params=params or {})

    def find_booking_by_ota_reservation_code(self, ota_reservation_code: str) -> dict[str, Any] | None:
        """Find a booking by OTA reservation code (e.g. Booking.com confirmation number)."""
        code = ota_reservation_code.strip()
        if not code:
            return None
        payload = self.list_bookings(
            params={
                "filter[ota_reservation_code]": code,
                "pagination[limit]": 1,
            }
        )
        data = payload.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return None

    def acknowledge_booking_revision(self, revision_id: str) -> None:
        self._request("POST", f"/booking_revisions/{revision_id}/ack")

    def list_booking_revisions_feed(self) -> list[str]:
        """Return non-acknowledged booking revision IDs (fallback for missed webhooks)."""
        payload = self._request("GET", "/booking_revisions/feed")
        revision_ids: list[str] = []
        for item in payload.get("data") or []:
            if isinstance(item, dict) and item.get("id"):
                revision_ids.append(str(item["id"]))
        return revision_ids

    def update_availability(self, values: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", "/availability", json={"values": values})

    def update_restrictions(self, values: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", "/restrictions", json={"values": values})

    def list_booking_messages(self, booking_id: str) -> dict[str, Any]:
        return self._request("GET", f"/bookings/{booking_id}/messages")

    def send_booking_message(self, booking_id: str, message: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/bookings/{booking_id}/messages",
            json={"message": {"message": message}},
        )

    def list_message_thread_messages(self, thread_id: str) -> dict[str, Any]:
        return self._request("GET", f"/message_threads/{thread_id}/messages")

    def report_no_show(self, booking_id: str, *, waived_fees: bool) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/bookings/{booking_id}/no_show",
            json={"no_show_report": {"waived_fees": waived_fees}},
        )

    @staticmethod
    def extract_task_ids(response: dict[str, Any]) -> list[str]:
        task_ids: list[str] = []
        for item in response.get("data") or []:
            if isinstance(item, dict) and item.get("type") == "task" and item.get("id"):
                task_ids.append(str(item["id"]))
        return task_ids
