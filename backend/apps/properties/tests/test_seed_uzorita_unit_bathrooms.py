from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.properties.models import Property, Unit, UnitBathroom
from apps.tenants.models import Tenant


class SeedUzoritaUnitBathroomsTests(TestCase):
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
            )

    def _run_seed(self):
        out = StringIO()
        call_command(
            "seed_uzorita_unit_bathrooms",
            tenant_slug=self.tenant.slug,
            stdout=out,
        )
        return out.getvalue()

    def test_seed_creates_one_bathroom_per_unit(self):
        self._run_seed()
        for code in ("R1", "R2", "R3", "R6"):
            baths = list(UnitBathroom.objects.filter(unit=self.units[code]))
            self.assertEqual(len(baths), 1)
            self.assertTrue(baths[0].is_private)
            self.assertTrue(baths[0].is_inside_room)

    def test_seed_is_idempotent(self):
        self._run_seed()
        self._run_seed()
        self.assertEqual(UnitBathroom.objects.filter(tenant=self.tenant).count(), 4)

    def test_seed_skips_missing_unit(self):
        self.units["R3"].delete()
        output = self._run_seed()
        self.assertIn("SKIP R3", output)
        self.assertEqual(UnitBathroom.objects.filter(tenant=self.tenant).count(), 3)
