from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.properties.models import Property
from apps.tenants.models import Tenant


class PropertyWhatsAppAutocheckinTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")

    def test_clean_requires_time_when_enabled(self):
        prop = Property(
            tenant=self.tenant,
            name="Test",
            slug="test",
            whatsapp_autocheckin_enabled=True,
            whatsapp_autocheckin_time=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            prop.clean()
        self.assertIn("whatsapp_autocheckin_time", ctx.exception.message_dict)

    def test_clean_passes_when_enabled_with_time(self):
        prop = Property(
            tenant=self.tenant,
            name="Test",
            slug="test",
            whatsapp_autocheckin_enabled=True,
            whatsapp_autocheckin_time=time(8, 0),
        )
        prop.clean()

    def test_defaults_disabled(self):
        prop = Property.objects.create(tenant=self.tenant, name="Test", slug="test")
        self.assertFalse(prop.whatsapp_autocheckin_enabled)
        self.assertEqual(prop.whatsapp_autocheckin_time, time(8, 0))
