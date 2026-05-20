from django.db import IntegrityError
from django.test import TestCase

from apps.properties.bathrooms import UZORITA_STANDARD_BATHROOM
from apps.properties.models import Property, Unit, UnitBathroom
from apps.tenants.models import Tenant


class UnitBathroomModelTests(TestCase):
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

    def test_standard_bathroom(self):
        spec = UZORITA_STANDARD_BATHROOM
        bath = UnitBathroom.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            is_private=spec["is_private"],
            is_inside_room=spec["is_inside_room"],
            sort_order=spec["sort_order"],
        )
        self.assertTrue(bath.is_private)
        self.assertTrue(bath.is_inside_room)

    def test_unique_sort_order_per_unit(self):
        UnitBathroom.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            is_private=True,
            is_inside_room=True,
            sort_order=0,
        )
        with self.assertRaises(IntegrityError):
            UnitBathroom.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                is_private=True,
                is_inside_room=False,
                sort_order=0,
            )

    def test_get_bathrooms_display_single(self):
        UnitBathroom.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            is_private=True,
            is_inside_room=True,
            sort_order=0,
        )
        self.assertEqual(
            self.unit.get_bathrooms_display(),
            "1 bathroom (private, en-suite)",
        )

    def test_get_bathrooms_display_multiple(self):
        for order in (0, 1):
            UnitBathroom.objects.create(
                tenant=self.tenant,
                unit=self.unit,
                is_private=True,
                is_inside_room=True,
                sort_order=order,
            )
        self.assertEqual(self.unit.get_bathrooms_display(), "2 bathrooms")
