from django.test import TestCase

from apps.api.serializers import UnitSummarySerializer
from apps.properties.models import BedType, Property, Unit, UnitBed, UnitBathroom
from apps.tenants.models import Tenant


class UnitSummarySerializerTests(TestCase):
    def test_includes_booking_occupancy_fields(self):
        tenant = Tenant.objects.create(slug="demo", name="Demo")
        prop = Property.objects.create(tenant=tenant, slug="demo", name="Demo Property")
        unit = Unit.objects.create(
            tenant=tenant,
            property=prop,
            code="R1",
            name="Room 1",
            capacity_max_guests=3,
            capacity_adults=2,
            capacity_children=2,
            capacity_infants=2,
        )

        data = UnitSummarySerializer(unit).data

        self.assertEqual(data["capacity_max_guests"], 3)
        self.assertEqual(data["capacity_adults"], 2)
        self.assertEqual(data["capacity_children"], 2)
        self.assertEqual(data["capacity_infants"], 2)

    def test_includes_beds(self):
        tenant = Tenant.objects.create(slug="demo2", name="Demo")
        prop = Property.objects.create(tenant=tenant, slug="demo2", name="Demo Property")
        unit = Unit.objects.create(
            tenant=tenant,
            property=prop,
            code="R1",
            name="Room 1",
        )
        UnitBed.objects.create(
            tenant=tenant,
            unit=unit,
            bed_type=BedType.QUEEN,
            count=1,
            sort_order=0,
        )
        UnitBed.objects.create(
            tenant=tenant,
            unit=unit,
            bed_type=BedType.SOFA,
            count=1,
            sort_order=1,
        )

        data = UnitSummarySerializer(unit).data

        self.assertEqual(len(data["beds"]), 2)
        self.assertEqual(data["beds"][0]["bed_type"], "queen")
        self.assertEqual(data["beds"][0]["count"], 1)
        self.assertIn("Queen bed(s)", data["beds"][0]["bed_type_label"])
        self.assertEqual(data["beds"][1]["bed_type"], "sofa")

    def test_includes_bathrooms(self):
        tenant = Tenant.objects.create(slug="demo3", name="Demo")
        prop = Property.objects.create(tenant=tenant, slug="demo3", name="Demo Property")
        unit = Unit.objects.create(
            tenant=tenant,
            property=prop,
            code="R1",
            name="Room 1",
        )
        UnitBathroom.objects.create(
            tenant=tenant,
            unit=unit,
            is_private=True,
            is_inside_room=True,
            sort_order=0,
        )

        data = UnitSummarySerializer(unit).data

        self.assertEqual(len(data["bathrooms"]), 1)
        self.assertTrue(data["bathrooms"][0]["is_private"])
        self.assertTrue(data["bathrooms"][0]["is_inside_room"])
        self.assertEqual(data["bathrooms"][0]["sort_order"], 0)
