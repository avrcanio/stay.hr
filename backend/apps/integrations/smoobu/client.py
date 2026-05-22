from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import httpx

from apps.integrations.smoobu.config import SmoobuRuntimeConfig
from apps.integrations.smoobu.exceptions import SmoobuApiError

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 3


class SmoobuClient:
    def __init__(self, config: SmoobuRuntimeConfig) -> None:
        self._config = config
        self._session = httpx.Client(
            timeout=30.0,
            headers={
                "Api-Key": config.api_key,
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "User-Agent": "stay.hr/1.0 (+https://stay.hr)",
            },
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> SmoobuClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return f"{self._config.api_base}{path}"

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._session.request(method, self._url(path), **kwargs)
            except httpx.HTTPError as exc:
                raise SmoobuApiError(f"Smoobu HTTP error: {exc}") from exc

            if response.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                retry_after = response.headers.get("X-RateLimit-Retry-After")
                wait_seconds = self._retry_wait_seconds(retry_after)
                logger.warning(
                    "Smoobu rate limit hit; retrying in %.1fs (attempt %s)",
                    wait_seconds,
                    attempt + 1,
                )
                time.sleep(wait_seconds)
                continue

            if response.status_code >= 400:
                body = response.text[:500]
                raise SmoobuApiError(
                    f"Smoobu {method} {path} failed ({response.status_code}): {body}"
                )

            if not response.content:
                return {}
            data = response.json()
            if not isinstance(data, dict):
                raise SmoobuApiError(f"Unexpected Smoobu response type for {path}")
            return data

        raise SmoobuApiError(f"Smoobu {method} {path} failed after rate-limit retries")

    @staticmethod
    def _retry_wait_seconds(retry_after: str | None) -> float:
        if not retry_after:
            return 60.0
        try:
            retry_ts = int(retry_after)
        except ValueError:
            return 60.0
        wait = retry_ts - int(time.time())
        return max(float(wait), 1.0)

    def get_rates(
        self,
        *,
        apartment_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        params: list[tuple[str, str | int]] = [
            ("start_date", start_date.isoformat()),
            ("end_date", end_date.isoformat()),
        ]
        for apartment_id in apartment_ids:
            params.append(("apartments[]", apartment_id))
        return self._request("GET", "/api/rates", params=params)

    def post_rates(
        self,
        *,
        apartment_ids: list[int],
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/rates",
            json={"apartments": apartment_ids, "operations": operations},
        )

    def create_reservation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/reservations", json=payload)

    def get_reservation(self, reservation_id: int | str) -> dict[str, Any]:
        return self._request("GET", f"/api/reservations/{reservation_id}")

    def get_reservations(
        self,
        *,
        modified_from: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        apartment_id: int | None = None,
        exclude_blocked: bool | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"page": page, "pageSize": page_size}
        if modified_from:
            params["modifiedFrom"] = modified_from
        if date_from is not None:
            params["from"] = date_from.isoformat()
        if date_to is not None:
            params["to"] = date_to.isoformat()
        if apartment_id is not None:
            params["apartmentId"] = apartment_id
        if exclude_blocked is not None:
            params["excludeBlocked"] = "true" if exclude_blocked else "false"
        return self._request("GET", "/api/reservations", params=params)

    def cancel_reservation(self, reservation_id: int | str) -> dict[str, Any]:
        return self._request("DELETE", f"/api/reservations/{reservation_id}")

    def iter_reservations(
        self,
        *,
        modified_from: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        apartment_id: int | None = None,
        exclude_blocked: bool | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        page = 1
        bookings: list[dict[str, Any]] = []
        while True:
            payload = self.get_reservations(
                modified_from=modified_from,
                date_from=date_from,
                date_to=date_to,
                apartment_id=apartment_id,
                exclude_blocked=exclude_blocked,
                page=page,
                page_size=page_size,
            )
            page_bookings = payload.get("bookings") or []
            if not isinstance(page_bookings, list):
                raise SmoobuApiError("Unexpected Smoobu reservations response: bookings is not a list")
            bookings.extend(item for item in page_bookings if isinstance(item, dict))

            page_count = int(payload.get("page_count") or 1)
            if page >= page_count:
                break
            page += 1
        return bookings
