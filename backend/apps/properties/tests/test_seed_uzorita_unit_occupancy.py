from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant


class SeedUzoritaUnitOccupancyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
        )
        self.units = {}
        for code in ("R1", "R2", "R3", "R6"):
            self.units[code] = Unit.objects.create(
                tenant=self.tenant,
                property=self.property,
                code=code,
                name=f"Room {code}",
                capacity_max_guests=2,
                capacity_adults=2,
                capacity_children=0,
                capacity_infants=0,
            )

    def _run_seed(self):
        out = StringIO()
        call_command(
            "seed_uzorita_unit_occupancy",
            tenant_slug=self.tenant.slug,
            stdout=out,
        )
        return out.getvalue()

    def test_seed_updates_r3_and_r6(self):
        self._run_seed()
        self.units["R1"].refresh_from_db()
        self.units["R3"].refresh_from_db()
        self.units["R6"].refresh_from_db()

        self.assertEqual(self.units["R1"].capacity_max_guests, 2)
        self.assertEqual(self.units["R1"].capacity_adults, 2)
        self.assertEqual(self.units["R1"].capacity_children, 1)
        self.assertEqual(self.units["R1"].capacity_infants, 1)
        self.units["R2"].refresh_from_db()
        self.assertEqual(self.units["R2"].capacity_max_guests, 3)
        self.assertEqual(self.units["R2"].capacity_adults, 2)
        self.assertEqual(self.units["R2"].capacity_children, 2)
        self.assertEqual(self.units["R2"].capacity_infants, 1)
        self.assertEqual(self.units["R3"].capacity_max_guests, 4)
        self.assertEqual(self.units["R3"].capacity_adults, 3)
        self.assertEqual(self.units["R3"].capacity_children, 3)
        self.assertEqual(self.units["R3"].capacity_infants, 3)
        self.assertEqual(self.units["R6"].capacity_max_guests, 4)
        self.assertEqual(self.units["R6"].capacity_adults, 3)
        self.assertEqual(self.units["R6"].capacity_children, 3)
        self.assertEqual(self.units["R6"].capacity_infants, 3)
