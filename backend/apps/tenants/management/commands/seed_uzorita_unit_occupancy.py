from django.core.management.base import BaseCommand
from django.db import transaction

from apps.properties.models import Property, Unit
from apps.properties.occupancy import UZORITA_OCCUPANCY_SEED_UNIT_CODES, UZORITA_UNIT_OCCUPANCY
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Set Booking.com / Channex occupancy on Uzorita units "
        "(R1: 2/2/1/1, R2: 3/2/2/1, R3/R6: 4 with 3 adults / 3 children / 3 infants)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument("--property-slug", default="uzorita")
        parser.add_argument(
            "--unit-codes",
            nargs="+",
            default=list(UZORITA_OCCUPANCY_SEED_UNIT_CODES),
            help="Unit codes to update (default: R1 R2 R3 R6).",
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

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Seeding occupancy for tenant={tenant.slug} property={prop.slug}"
            )
        )

        updated = 0
        for code in unit_codes:
            spec = UZORITA_UNIT_OCCUPANCY.get(code)
            if spec is None:
                self.stdout.write(self.style.WARNING(f"  SKIP {code} — no occupancy spec"))
                continue

            unit = Unit.objects.filter(tenant=tenant, property=prop, code=code).first()
            if unit is None:
                self.stdout.write(self.style.WARNING(f"  SKIP {code} — unit not found"))
                continue

            for field, value in spec.items():
                setattr(unit, field, value)
            unit.full_clean()
            unit.save(update_fields=[*spec.keys(), "updated_at"])
            updated += 1
            self.stdout.write(f"  {unit.code}: {unit.get_capacity_display()}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done — updated {updated} unit(s)."))
