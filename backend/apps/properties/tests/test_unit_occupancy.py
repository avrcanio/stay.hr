from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant


class UnitOccupancyValidationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="test", name="Test")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="test-prop",
            name="Test Property",
        )

    def _unit(self, **overrides) -> Unit:
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "code": "R1",
            "name": "Room 1",
            "capacity_max_guests": 3,
            "capacity_adults": 2,
            "capacity_children": 2,
            "capacity_infants": 2,
        }
        defaults.update(overrides)
        return Unit(**defaults)

    def test_valid_booking_style_occupancy(self):
        unit = self._unit()
        unit.full_clean()

    def test_adults_cannot_exceed_max_guests(self):
        unit = self._unit(capacity_max_guests=3, capacity_adults=4, capacity_children=0)
        with self.assertRaises(ValidationError) as ctx:
            unit.full_clean()
        self.assertIn("capacity_adults", ctx.exception.message_dict)

    def test_children_must_be_less_than_max_guests(self):
        unit = self._unit(capacity_max_guests=3, capacity_adults=2, capacity_children=3)
        with self.assertRaises(ValidationError) as ctx:
            unit.full_clean()
        self.assertIn("capacity_children", ctx.exception.message_dict)

    def test_max_guests_cannot_exceed_adults_plus_children(self):
        unit = self._unit(capacity_max_guests=5, capacity_adults=2, capacity_children=2)
        with self.assertRaises(ValidationError) as ctx:
            unit.full_clean()
        self.assertIn("capacity_max_guests", ctx.exception.message_dict)

    def test_capacity_display(self):
        unit = self._unit()
        self.assertEqual(
            unit.get_capacity_display(),
            "3 guests / 2 adults / 2 children / 2 infants",
        )
