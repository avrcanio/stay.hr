"""Uzorita Property.guest_info seed payload."""

from __future__ import annotations

from apps.communications.guest_compose_defaults import (
    DEFAULT_ENTRANCE_IMAGE,
    DEFAULT_TEXTS,
    MAPS_LINK,
)

UZORITA_AI_NOTES = (
    "Accommodation rooms are above Restaurant Uzorita — look for the ROOMS sign at the entrance. "
    "Check-in from 15:00. Free parking throughout the zone; you may park in front of the restaurant "
    "or nearby. Please let us know your approximate arrival time."
)

UZORITA_GUEST_INFO: dict = {
    "links": {
        "maps_url": MAPS_LINK,
    },
    "assets": {
        "entrance_image": DEFAULT_ENTRANCE_IMAGE,
    },
    "facts": {
        "ai_notes": UZORITA_AI_NOTES,
        "reception_hours": "08:00–22:00",
        "wifi": {
            "ssid": "Uzoritarooms",
            "password": "77777777",
        },
        "parking": {
            "has_private": True,
            "zone_label": "cijela zona (besplatno)",
            "price_per_day": "0",
            "currency": "EUR",
            "large_vehicles_allowed": True,
            "custom": {
                "hr": (
                    "Možete parkirati ispred restorana ako ima mjesta, "
                    "ili bilo gdje u neposrednoj blizini."
                ),
                "en": (
                    "You may park in front of the restaurant if there is space, "
                    "or anywhere nearby."
                ),
            },
        },
    },
    "texts": dict(DEFAULT_TEXTS),
}
