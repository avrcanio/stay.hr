from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TENANT_SLUG = "mango-vodice"
PROPERTY_SLUG = "mango-vodice"
DOMAIN = "mango-vodice.stay.hr"
UNIT_CODE = "APT-01"
UNIT_NAME = "Apartman s 3 spavaće sobe"
UNIT_MAX_GUESTS = 7
UNIT_ADULTS = 7

DEFAULT_NAME = "Mango Tourist Apartment"
DEFAULT_ADDRESS = "83 Brunac ulica, 22211 Vodice, Hrvatska"
DEFAULT_DESCRIPTION = (
    "Objekt Mango Tourist Apartment nalazi se u Vodicama na 13 km od znamenitosti "
    "Barone Fortress, 13 km od znamenitosti Gradska vijećnica u Šibeniku i 36 km "
    "od znamenitosti Marina Kornati te nudi smještaj s balkonom i besplatnim WiFi-jem."
)
DEFAULT_IMAGE = (
    "https://cf.bstatic.com/xdata/images/hotel/max500/520728813.jpg"
    "?k=35b5a55eabaa21bba1490d9d5adcab1302b5d3a8ae1fbca22fce2b13ea322699&o=&hp=1"
)
DEFAULT_PRIMARY_COLOR = "#e67e22"


@dataclass(frozen=True)
class MangoSeedData:
    name: str
    address: str
    description: str
    hero_image_url: str


def extract_ld_json(html: str) -> dict | None:
    marker = 'type="application/ld+json"'
    idx = html.find(marker)
    if idx == -1:
        return None

    start = html.find("{", idx)
    if start == -1:
        return None

    depth = 0
    for pos in range(start, len(html)):
        char = html[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : pos + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _address_from_ld_json(payload: dict) -> str | None:
    address = payload.get("address")
    if isinstance(address, dict):
        street = address.get("streetAddress")
        if isinstance(street, str) and street.strip():
            return street.strip()
    return None


def load_mango_seed_data(html_path: Path | None) -> MangoSeedData:
    defaults = MangoSeedData(
        name=DEFAULT_NAME,
        address=DEFAULT_ADDRESS,
        description=DEFAULT_DESCRIPTION,
        hero_image_url=DEFAULT_IMAGE,
    )
    if html_path is None or not html_path.is_file():
        return defaults

    html = html_path.read_text(encoding="utf-8", errors="replace")
    payload = extract_ld_json(html)
    if not payload:
        return defaults

    name = payload.get("name")
    description = payload.get("description")
    image = payload.get("image")
    address = _address_from_ld_json(payload)

    return MangoSeedData(
        name=name.strip() if isinstance(name, str) and name.strip() else defaults.name,
        address=address or defaults.address,
        description=(
            description.strip()
            if isinstance(description, str) and description.strip()
            else defaults.description
        ),
        hero_image_url=(
            image.strip() if isinstance(image, str) and image.strip() else defaults.hero_image_url
        ),
    )


def default_html_path() -> Path:
    return Path(__file__).resolve().parents[3] / "mango.html"
