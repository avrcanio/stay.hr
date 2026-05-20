from django.core.management.base import BaseCommand
from django.db import transaction

from apps.properties.bathrooms import (
    UZORITA_BATHROOM_SEED_UNIT_CODES,
    UZORITA_STANDARD_BATHROOM,
)
from apps.properties.models import Property, Unit, UnitBathroom
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Seed Booking.com bathroom config (1 private en-suite bathroom) "
        "for Uzorita units R1, R2, R3, R6."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument("--property-slug", default="uzorita")
        parser.add_argument(
            "--unit-codes",
            nargs="+",
            default=list(UZORITA_BATHROOM_SEED_UNIT_CODES),
            help="Unit codes to seed (default: R1 R2 R3 R6).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {options['tenant_slug']}"))
            return

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        if prop is None:
            self.stderr.write(
                self.style.ERROR(
                    f"Property not found: {options['property_slug']} "
                    f"(tenant {options['tenant_slug']})"
                )
            )
            return

        unit_codes = [code.strip().upper() for code in options["unit_codes"] if code.strip()]
        total = 0

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Seeding bathrooms for tenant={tenant.slug} property={prop.slug}"
            )
        )

        spec = UZORITA_STANDARD_BATHROOM
        for code in unit_codes:
            unit = Unit.objects.filter(tenant=tenant, property=prop, code=code).first()
            if unit is None:
                self.stdout.write(self.style.WARNING(f"  SKIP {code} — unit not found"))
                continue

            deleted, _ = UnitBathroom.objects.filter(tenant=tenant, unit=unit).delete()
            UnitBathroom.objects.create(
                tenant=tenant,
                unit=unit,
                is_private=spec["is_private"],
                is_inside_room=spec["is_inside_room"],
                sort_order=spec["sort_order"],
            )
            total += 1
            self.stdout.write(
                f"  {unit.code}: replaced {deleted} bathroom row(s), created 1 "
                f"({unit.get_bathrooms_display()})"
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done — {total} bathroom row(s) across {len(unit_codes)} unit code(s)."
            )
        )
