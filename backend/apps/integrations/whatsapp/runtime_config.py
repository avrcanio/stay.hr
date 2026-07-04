from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.integrations.whatsapp.config import access_token_from_env, waba_id_from_env


@dataclass(frozen=True)
class WhatsAppRuntimeConfig:
    phone_number_id: str
    display_phone_number: str = ""
    waba_id: str = ""
    auto_reply: bool = True

    @classmethod
    def from_integration_dict(cls, data: dict[str, Any]) -> WhatsAppRuntimeConfig:
        auto_reply = data.get("auto_reply", True)
        if isinstance(auto_reply, str):
            auto_reply = auto_reply.strip().lower() not in ("0", "false", "no", "off")

        return cls(
            phone_number_id=str(data.get("phone_number_id") or "").strip(),
            display_phone_number=str(data.get("display_phone_number") or "").strip(),
            waba_id=str(data.get("waba_id") or "").strip(),
            auto_reply=bool(auto_reply),
        )

    @property
    def access_token(self) -> str:
        return access_token_from_env()

    def effective_waba_id(self) -> str:
        return self.waba_id or waba_id_from_env()

    def send_credentials_ok(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def can_send_messages(self) -> bool:
        return self.send_credentials_ok()

    def can_send_media(self) -> bool:
        return self.can_send_messages()
