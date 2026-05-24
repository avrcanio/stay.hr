from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tourist_tax.models import TouristTaxZone
from apps.tourist_tax.seed.common import seed_ordinance

ORDINANCE = {
    "code": "vodice",
    "name": "Odluka o visini turističke pristojbe — Grad Vodice",
    "issuer": "Grad Vodice",
    "valid_from": date(2024, 1, 1),
}

ZONES = [
    {
        "code": "vodice",
        "kind": TouristTaxZone.Kind.CENTRAL,
        "name": "Grad Vodice",
        "settlements": ["Vodice"],
        "rates": {
            "main": Decimal("1.80"),
            "off": Decimal("1.33"),
        },
    },
]


class Command(BaseCommand):
    help = "Seed tourist tax reference data for Grad Vodice (idempotent)."

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
            "\nNext: in Django admin, set Property → tourist_tax_zone to "
            "vodice and tourist_tax_category (e.g. room or apartment)."
        )
