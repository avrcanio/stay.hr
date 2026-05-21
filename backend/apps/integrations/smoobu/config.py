from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from apps.integrations.smoobu.mapping import SMOOBU_API_BASE


@dataclass(frozen=True)
class SmoobuApartmentLink:
    unit_code: str
    smoobu_apartment_id: int
    unit_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SmoobuApartmentLink:
        unit_id = data.get("unit_id")
        return cls(
            unit_code=str(data["unit_code"]),
            smoobu_apartment_id=int(data["smoobu_apartment_id"]),
            unit_id=int(unit_id) if unit_id is not None else None,
        )


@dataclass(frozen=True)
class SmoobuRuntimeConfig:
    api_base: str
    api_key: str
    settings_channel_id: int | None = None
    apartments: tuple[SmoobuApartmentLink, ...] = field(default_factory=tuple)
    push_rates_enabled: bool = True
    default_channel_id_for_create: int = 70

    @classmethod
    def from_integration_dict(cls, data: dict[str, Any]) -> SmoobuRuntimeConfig:
        rows = data.get("apartments") or []
        apartments = tuple(
            SmoobuApartmentLink.from_dict(row)
            for row in rows
            if row.get("unit_code") and row.get("smoobu_apartment_id") is not None
        )
        channel_id = data.get("settings_channel_id")
        return cls(
            api_base=str(data.get("api_base") or SMOOBU_API_BASE).rstrip("/"),
            api_key=str(data.get("api_key") or os.getenv("SMOOBU_API_KEY", "")).strip(),
            settings_channel_id=int(channel_id) if channel_id is not None else None,
            apartments=apartments,
            push_rates_enabled=bool(data.get("push_rates_enabled", True)),
            default_channel_id_for_create=int(data.get("default_channel_id_for_create") or 70),
        )

    def apartment_id_for_unit_code(self, unit_code: str) -> int | None:
        for link in self.apartments:
            if link.unit_code == unit_code:
                return link.smoobu_apartment_id
        return None

    def link_for_apartment_id(self, apartment_id: int) -> SmoobuApartmentLink | None:
        for link in self.apartments:
            if link.smoobu_apartment_id == apartment_id:
                return link
        return None
