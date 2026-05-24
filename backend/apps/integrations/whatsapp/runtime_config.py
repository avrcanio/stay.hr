from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WhatsAppRuntimeConfig:
    phone_number_id: str
    display_phone_number: str
    waba_id: str
    access_token: str
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
            access_token=str(data.get("access_token") or "").strip(),
            auto_reply=bool(auto_reply),
        )
