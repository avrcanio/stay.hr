from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.properties.models import Property, SelfServiceMode
from apps.properties.self_service import is_self_service_active, normalize_self_service_config
from apps.tenants.models import Tenant


class SelfServiceActiveTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="SS Tenant", slug="ss-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="SS Property",
            slug="ss-property",
        )

    def test_off_is_never_active(self):
        self.property.self_service_mode = SelfServiceMode.OFF
        self.property.self_service_config = {"weekdays": [1]}
        self.assertFalse(is_self_service_active(self.property, date(2026, 7, 21)))

    def test_always_is_active(self):
        self.property.self_service_mode = SelfServiceMode.ALWAYS
        self.assertTrue(is_self_service_active(self.property, date(2026, 7, 20)))

    def test_schedule_tuesday_only(self):
        self.property.self_service_mode = SelfServiceMode.SCHEDULE
        self.property.self_service_config = {"weekdays": [1]}  # Tuesday
        tuesday = date(2026, 7, 21)
        wednesday = date(2026, 7, 22)
        self.assertEqual(tuesday.weekday(), 1)
        self.assertTrue(is_self_service_active(self.property, tuesday))
        self.assertFalse(is_self_service_active(self.property, wednesday))

    def test_calendar_dates(self):
        self.property.self_service_mode = SelfServiceMode.CALENDAR
        self.property.self_service_config = {"dates": ["2026-07-24"]}
        self.assertTrue(is_self_service_active(self.property, date(2026, 7, 24)))
        self.assertFalse(is_self_service_active(self.property, date(2026, 7, 25)))

    def test_normalize_self_service_config(self):
        cfg = normalize_self_service_config(
            {"weekdays": [1, "1", 9, "x"], "dates": ["2026-07-24", "bad", "2026-07-24"]}
        )
        self.assertEqual(cfg["weekdays"], [1])
        self.assertEqual(cfg["dates"], ["2026-07-24"])
