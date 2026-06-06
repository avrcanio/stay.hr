from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.integrations.whatsapp.config import (
    d360_api_base_url_from_env,
    d360_api_key_from_env,
    is_360dialog_provider,
    provider_from_env,
)


@dataclass(frozen=True)
class WhatsAppRuntimeConfig:
    phone_number_id: str
    display_phone_number: str
    waba_id: str
    access_token: str
    provider: str = "meta"
    api_base_url: str = ""
    auto_reply: bool = True

    @classmethod
    def from_integration_dict(cls, data: dict[str, Any]) -> WhatsAppRuntimeConfig:
        auto_reply = data.get("auto_reply", True)
        if isinstance(auto_reply, str):
            auto_reply = auto_reply.strip().lower() not in ("0", "false", "no", "off")

        provider = str(data.get("provider") or provider_from_env() or "meta").strip().lower()
        access_token = str(data.get("access_token") or "").strip()
        if is_360dialog_provider(provider) and not access_token:
            access_token = d360_api_key_from_env()

        api_base_url = str(data.get("api_base_url") or "").strip()
        if is_360dialog_provider(provider) and not api_base_url:
            api_base_url = d360_api_base_url_from_env()

        return cls(
            phone_number_id=str(data.get("phone_number_id") or "").strip(),
            display_phone_number=str(data.get("display_phone_number") or "").strip(),
            waba_id=str(data.get("waba_id") or "").strip(),
            access_token=access_token,
            provider=provider,
            api_base_url=api_base_url,
            auto_reply=bool(auto_reply),
        )

    def send_credentials_ok(self) -> bool:
        if is_360dialog_provider(self.provider):
            return bool(self.access_token)
        return bool(self.access_token and self.phone_number_id)
