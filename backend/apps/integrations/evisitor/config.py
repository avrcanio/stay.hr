from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvisitorRuntimeConfig:
    enabled: bool
    env: str
    base_url: str
    username: str
    password: str
    api_key: str
    facility_code: str
    default_arrival_organisation: str
    default_offered_service_type: str
    default_payment_category: str
    default_stay_time_from: str
    default_stay_time_until: str

    @classmethod
    def from_integration_dict(cls, data: dict[str, Any]) -> EvisitorRuntimeConfig:
        enabled = bool(data.get("enabled"))
        env = (data.get("env") or "test").strip().lower()
        return cls(
            enabled=enabled,
            env=env,
            base_url=(data.get("base_url") or "").strip(),
            username=(data.get("username") or "").strip(),
            password=(data.get("password") or "").strip(),
            api_key=(data.get("api_key") or "").strip(),
            facility_code=(data.get("facility_code") or "").strip(),
            default_arrival_organisation=(
                data.get("default_arrival_organisation") or "I"
            ).strip(),
            default_offered_service_type=(
                data.get("default_offered_service_type") or "noćenje"
            ).strip(),
            default_payment_category=(data.get("default_payment_category") or "14").strip(),
            default_stay_time_from=(data.get("default_stay_time_from") or "14:00").strip(),
            default_stay_time_until=(data.get("default_stay_time_until") or "10:00").strip(),
        )
