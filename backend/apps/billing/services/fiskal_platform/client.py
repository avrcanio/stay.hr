from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from django.conf import settings

from apps.billing.exceptions import FiscalizationError

TERMINAL_STATUSES = frozenset({"accepted", "failed", "dead"})


@dataclass(frozen=True)
class SubmitResult:
    request_id: UUID
    status: str
    correlation_id: str
    idempotent_replay: bool = False


@dataclass(frozen=True)
class ExecutionStatus:
    request_id: UUID
    status: str
    jir: str | None = None
    zki: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    correlation_id: str | None = None


def _parse_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:1000] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        code = payload.get("error_code") or payload.get("code")
        message = payload.get("message") or payload.get("detail") or response.text[:500]
        if code:
            return f"{code}: {message}"
        return str(message)
    return response.text[:1000]


class FiskalExecutionClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or settings.FISKAL_PLATFORM_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.FISKAL_PLATFORM_API_KEY
        self._http_client = http_client
        self._timeout = timeout
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self.base_url,
                timeout=self._timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._http_client

    def submit_execution(
        self,
        body: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> SubmitResult:
        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        else:
            headers["X-Correlation-ID"] = str(uuid.uuid4())

        response = self._client().post("/api/v2/executions", json=body, headers=headers)
        if response.status_code == 202:
            data = response.json()
            return SubmitResult(
                request_id=UUID(str(data["request_id"])),
                status=str(data.get("status", "received")),
                correlation_id=str(data.get("correlation_id", "")),
                idempotent_replay=bool(data.get("idempotent_replay", False)),
            )
        self._raise_for_response(response)

    def get_execution(self, request_id: UUID | str) -> ExecutionStatus:
        response = self._client().get(f"/api/v2/executions/{request_id}")
        if response.status_code == 200:
            data = response.json()
            return ExecutionStatus(
                request_id=UUID(str(data.get("id") or data.get("request_id") or request_id)),
                status=str(data.get("status", "")).lower(),
                jir=data.get("jir"),
                zki=data.get("zki"),
                error_code=data.get("error_code"),
                error_message=data.get("error_message"),
                correlation_id=data.get("correlation_id"),
            )
        self._raise_for_response(response)

    def poll_until_terminal(
        self,
        request_id: UUID | str,
        *,
        interval: float | None = None,
        timeout: float | None = None,
    ) -> ExecutionStatus:
        poll_interval = (
            float(interval)
            if interval is not None
            else float(settings.FISKAL_EXECUTION_POLL_INTERVAL)
        )
        poll_timeout = (
            float(timeout)
            if timeout is not None
            else float(settings.FISKAL_EXECUTION_POLL_TIMEOUT)
        )
        deadline = time.monotonic() + poll_timeout
        last_status: ExecutionStatus | None = None

        while time.monotonic() < deadline:
            last_status = self.get_execution(request_id)
            if last_status.status in TERMINAL_STATUSES:
                return last_status
            time.sleep(poll_interval)

        status_label = last_status.status if last_status else "unknown"
        raise FiscalizationError(
            f"Fiskal execution poll timeout after {poll_timeout:.0f}s "
            f"(request_id={request_id}, last_status={status_label})",
            fiskal_request_id=request_id,
        )

    def _raise_for_response(self, response: httpx.Response) -> None:
        message = _parse_error_message(response)
        if response.status_code in {401, 403, 422, 429}:
            raise FiscalizationError(message)
        response.raise_for_status()
        raise FiscalizationError(message)
