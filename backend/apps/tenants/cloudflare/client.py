from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings


class CloudflareAPIError(Exception):
    def __init__(self, message: str, *, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or []


class CloudflareClient:
    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(self, token: str | None = None):
        self.token = token or settings.CF_DNS_API_TOKEN
        if not self.token:
            raise CloudflareAPIError("CF_DNS_API_TOKEN is not configured")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method,
                f"{self.BASE_URL}{path}",
                headers=headers,
                json=json_data,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CloudflareAPIError(
                f"Cloudflare API returned non-JSON response ({response.status_code})",
            ) from exc

        if not payload.get("success"):
            errors = payload.get("errors") or []
            messages = ", ".join(
                str(item.get("message", item)) for item in errors
            ) or f"HTTP {response.status_code}"
            raise CloudflareAPIError(messages, errors=errors)
        return payload

    def verify_token(self) -> None:
        self._request("GET", "/user/tokens/verify")

    def get_zone_id(self, zone_name: str) -> str:
        payload = self._request("GET", f"/zones?name={zone_name}&status=active")
        zones = payload.get("result") or []
        if not zones:
            raise CloudflareAPIError(f"Zone {zone_name!r} not found in Cloudflare account")
        return zones[0]["id"]

    def get_apex_a_record_ip(self, zone_id: str, zone_name: str) -> str | None:
        payload = self._request(
            "GET",
            f"/zones/{zone_id}/dns_records?type=A&name={zone_name}",
        )
        for record in payload.get("result") or []:
            if record.get("type") == "A" and record.get("content"):
                return record["content"]
        return None

    def upsert_a_record(
        self,
        zone_id: str,
        fqdn: str,
        ip: str,
        *,
        proxied: bool = True,
    ) -> str:
        list_payload = self._request(
            "GET",
            f"/zones/{zone_id}/dns_records?name={fqdn}",
        )
        records = list_payload.get("result") or []
        body = {
            "type": "A",
            "name": fqdn,
            "content": ip,
            "ttl": 1,
            "proxied": proxied,
        }

        for record in records:
            record_id = record["id"]
            if record.get("type") == "A" and record.get("content") == ip:
                if record.get("proxied") == proxied:
                    return record_id
                self._request(
                    "PUT",
                    f"/zones/{zone_id}/dns_records/{record_id}",
                    json_data=body,
                )
                return record_id
            self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")

        create_payload = self._request(
            "POST",
            f"/zones/{zone_id}/dns_records",
            json_data=body,
        )
        return create_payload["result"]["id"]
