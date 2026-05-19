from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChannexBookingTestRoomLink:
    unit_code: str
    channex_room_type_id: str
    channex_title: str
    unit_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannexBookingTestRoomLink:
        unit_id = data.get("unit_id")
        return cls(
            unit_code=str(data["unit_code"]),
            channex_room_type_id=str(data["channex_room_type_id"]),
            channex_title=str(data.get("channex_title") or data.get("booking_title") or ""),
            unit_id=int(unit_id) if unit_id is not None else None,
        )


@dataclass(frozen=True)
class ChannexRoomTypeLink:
    unit_code: str
    channex_room_type_id: str
    channex_title: str
    unit_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannexRoomTypeLink:
        unit_id = data.get("unit_id")
        return cls(
            unit_code=str(data["unit_code"]),
            channex_room_type_id=str(data["channex_room_type_id"]),
            channex_title=str(data.get("channex_title", "")),
            unit_id=int(unit_id) if unit_id is not None else None,
        )


@dataclass(frozen=True)
class ChannexRuntimeConfig:
    environment: str
    base_url: str
    property_id: str
    api_key: str
    webhook_secret: str = ""
    certification_property_slug: str = ""
    room_types: tuple[ChannexRoomTypeLink, ...] = field(default_factory=tuple)
    booking_test_rooms: tuple[ChannexBookingTestRoomLink, ...] = field(default_factory=tuple)

    @classmethod
    def from_integration_dict(cls, data: dict[str, Any]) -> ChannexRuntimeConfig:
        env = str(data.get("environment") or "staging").strip().lower()
        default_base = (
            "https://staging.channex.io/api/v1"
            if env == "staging"
            else "https://app.channex.io/api/v1"
        )
        room_rows = data.get("room_types") or []
        room_types = tuple(ChannexRoomTypeLink.from_dict(row) for row in room_rows if row.get("unit_code"))
        booking_rows = data.get("booking_test_rooms") or []
        booking_test_rooms = tuple(
            ChannexBookingTestRoomLink.from_dict(row) for row in booking_rows if row.get("unit_code")
        )
        api_key = str(data.get("api_key") or os.getenv("CHANNEX_API_KEY", "")).strip()
        webhook_secret = str(
            data.get("webhook_secret") or os.getenv("CHANNEX_WEBHOOK_SECRET", "")
        ).strip()
        return cls(
            environment=env,
            base_url=str(data.get("base_url") or default_base).rstrip("/"),
            property_id=str(data.get("property_id") or os.getenv("CHANNEX_PROPERTY_ID", "")).strip(),
            api_key=api_key,
            webhook_secret=webhook_secret,
            certification_property_slug=str(data.get("certification_property_slug") or "").strip(),
            room_types=room_types,
            booking_test_rooms=booking_test_rooms,
        )

    def room_type_id_for_unit_code(self, unit_code: str) -> str | None:
        for link in self.room_types:
            if link.unit_code == unit_code:
                return link.channex_room_type_id
        return None

    def unit_code_for_room_type_id(self, channex_room_type_id: str) -> str | None:
        for link in self.room_types:
            if link.channex_room_type_id == channex_room_type_id:
                return link.unit_code
        return None

    def booking_test_room_for_channex_room_type_id(
        self, channex_room_type_id: str
    ) -> ChannexBookingTestRoomLink | None:
        for link in self.booking_test_rooms:
            if link.channex_room_type_id == channex_room_type_id:
                return link
        return None
