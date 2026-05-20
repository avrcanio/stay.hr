from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.properties.beds import UZORITA_STANDARD_BEDS
from apps.properties.models import BedType, Property, Unit, UnitBed
from apps.tenants.models import Tenant


class UnitBedModelTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="test", name="Test")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="test-prop",
            name="Test Property",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="Room 1",
        )

    def test_valid_unit_bed(self):
        bed = UnitBed(
            tenant=self.tenant,
            unit=self.unit,
            bed_type=BedType.QUEEN,
            count=1,
        )
        bed.full_clean()

    def test_invalid_count(self):
        bed = UnitBed(
            tenant=self.tenant,
            unit=self.unit,
            bed_type=BedType.QUEEN,
            count=0,
        )
        with self.assertRaises(ValidationError):
            bed.full_clean()

    def test_unique_bed_type_per_unit(self):
        UnitBed.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            bed_type=BedType.QUEEN,
            count=1,
        )
        with self.assertRaises(IntegrityError):
            UnitBed.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                bed_type=BedType.QUEEN,
                count=2,
            )

    def test_get_beds_display(self):
        for spec in UZORITA_STANDARD_BEDS:
            UnitBed.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                bed_type=spec["bed_type"],
                count=spec["count"],
                sort_order=spec["sort_order"],
            )
        self.assertEqual(
            self.unit.get_beds_display(),
            "Queen bed(s) x1, Sofa bed x1",
        )
