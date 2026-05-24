from django.test import TestCase

from apps.properties.models import Property
from apps.properties.resolution import PropertyResolutionError, resolve_property_for_tenant
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class ResolvePropertyForTenantTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Multi Hotel", slug="multi-hotel")
        self.prop_a = Property.objects.create(
            tenant=self.tenant,
            name="Property A",
            slug="property-a",
        )
        self.prop_b = Property.objects.create(
            tenant=self.tenant,
            name="Property B",
            slug="property-b",
        )

    def test_reservation_property_takes_priority(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.prop_b,
            check_in="2026-06-01",
            check_out="2026-06-03",
            booker_name="Guest",
        )

        resolved = resolve_property_for_tenant(
            self.tenant,
            slug="property-a",
            reservation=reservation,
        )

        self.assertEqual(resolved, self.prop_b)

    def test_slug_lookup(self):
        resolved = resolve_property_for_tenant(self.tenant, slug="property-a")
        self.assertEqual(resolved, self.prop_a)

    def test_unknown_slug_raises(self):
        with self.assertRaises(PropertyResolutionError) as ctx:
            resolve_property_for_tenant(self.tenant, slug="missing")
        self.assertIn("property_slug", ctx.exception.message_dict)

    def test_multiple_properties_without_slug_raises(self):
        with self.assertRaises(PropertyResolutionError) as ctx:
            resolve_property_for_tenant(self.tenant)
        self.assertIn("property_slug", ctx.exception.message_dict)

    def test_single_property_tenant_resolves_without_slug(self):
        single_tenant = Tenant.objects.create(name="Solo", slug="solo")
        solo_prop = Property.objects.create(
            tenant=single_tenant,
            name="Solo Property",
            slug="solo-property",
        )

        resolved = resolve_property_for_tenant(single_tenant)

        self.assertEqual(resolved, solo_prop)

    def test_no_properties_raises(self):
        empty_tenant = Tenant.objects.create(name="Empty", slug="empty")

        with self.assertRaises(PropertyResolutionError) as ctx:
            resolve_property_for_tenant(empty_tenant)
        self.assertIn("property_slug", ctx.exception.message_dict)
