"""Load golden document-intake fixtures into test database objects."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant

_FIXTURES_ROOT = Path(__file__).resolve().parent


def fixture_dir(scenario: str) -> Path:
    path = _FIXTURES_ROOT / scenario
    if not path.is_dir():
        raise FileNotFoundError(f"document intake fixture not found: {scenario}")
    return path


def load_fixture_json(scenario: str, name: str) -> dict[str, Any]:
    path = fixture_dir(scenario) / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_document_intake_fixture(scenario: str) -> dict[str, Any]:
    """Return reservation, ocr, and optional whatsapp metadata for a scenario."""
    base = fixture_dir(scenario)
    data: dict[str, Any] = {
        "reservation": load_fixture_json(scenario, "reservation.json"),
        "ocr": load_fixture_json(scenario, "ocr.json"),
    }
    whatsapp_path = base / "whatsapp.json"
    if whatsapp_path.exists():
        data["whatsapp"] = json.loads(whatsapp_path.read_text(encoding="utf-8"))
    return data


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _reservation_status(raw: str) -> str:
    mapping = {
        "expected": Reservation.Status.EXPECTED,
        "checked_in": Reservation.Status.CHECKED_IN,
    }
    return mapping.get(raw.lower(), Reservation.Status.EXPECTED)


def build_reservation_from_fixture(
    *,
    tenant: Tenant,
    property: Property,
    scenario: str,
) -> tuple[Reservation, list[Guest], dict[str, Any], dict[str, Any]]:
    """Create Reservation + guests from fixture; return (reservation, guests, ocr, meta)."""
    fixture = load_document_intake_fixture(scenario)
    reservation_data = fixture["reservation"]
    ocr_data = fixture["ocr"]

    reservation = Reservation.objects.create(
        tenant=tenant,
        property=property,
        external_id=f"fixture-{scenario}",
        booking_code=f"fixture-{scenario}",
        check_in=_parse_date(reservation_data["check_in"]),
        check_out=_parse_date(reservation_data["check_out"]),
        status=_reservation_status(reservation_data.get("status", "expected")),
        booker_name=reservation_data["booker_name"],
        adults_count=reservation_data.get("adults_count", 1),
        children_count=reservation_data.get("children_count", 0),
        persons_count=reservation_data.get("persons_count"),
    )

    guests: list[Guest] = []
    for guest_data in reservation_data.get("guests") or []:
        guest = Guest.objects.create(
            tenant=tenant,
            reservation=reservation,
            first_name=guest_data["first_name"],
            last_name=guest_data["last_name"],
            name=guest_data.get("name") or f"{guest_data['first_name']} {guest_data['last_name']}".strip(),
            is_primary=bool(guest_data.get("is_primary")),
        )
        guests.append(guest)

    meta = {
        "scenario": scenario,
        "whatsapp": fixture.get("whatsapp"),
    }
    return reservation, guests, ocr_data, meta
