from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tourist_tax.models import TouristTaxZone
from apps.tourist_tax.seed.common import seed_ordinance

ORDINANCE = {
    "code": "sibenik",
    "name": "Odluka o visini turističke pristojbe — Šibensko-kninska županija (Grad Šibenik)",
    "issuer": "Šibensko-kninska županija",
    "valid_from": date(2024, 1, 1),
}

ZONES = [
    {
        "code": "sibenik-central",
        "kind": TouristTaxZone.Kind.CENTRAL,
        "name": "Uže gradsko jezgro i turistička naselja",
        "settlements": [
            "Šibenik",
            "Brodarica",
            "Grebaštica",
            "Žaborić",
            "Zlarin",
            "Prvić",
        ],
        "rates": {
            "main": Decimal("2.50"),
            "off": Decimal("1.80"),
        },
    },
    {
        "code": "sibenik-peripheral",
        "kind": TouristTaxZone.Kind.PERIPHERAL,
        "name": "Okolna naselja (zaleđe)",
        "settlements": ["Dubrava", "Danilo", "Pakovo Selo"],
        "rates": {
            "main": Decimal("1.33"),
            "off": Decimal("1.00"),
        },
    },
]


class Command(BaseCommand):
    help = "Seed tourist tax reference data for Grad Šibenik (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        _, rate_count = seed_ordinance(
            code=ORDINANCE["code"],
            name=ORDINANCE["name"],
            issuer=ORDINANCE["issuer"],
            valid_from=ORDINANCE["valid_from"],
            zones=ZONES,
            stdout=self.stdout,
        )

        self.stdout.write(self.style.SUCCESS(f"Seed complete ({rate_count} rates)."))
        self.stdout.write(
            "\nNext: in Django admin, set Property → tourist_tax_zone and "
            "tourist_tax_category (e.g. sibenik-central + room for Uzorita)."
        )
