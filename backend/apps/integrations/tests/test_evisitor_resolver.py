from datetime import time

from django.test import TestCase

from apps.integrations.evisitor.config import EvisitorRuntimeConfig
from apps.integrations.evisitor.exceptions import EvisitorConfigError
from apps.integrations.evisitor.resolver import resolve_evisitor_config
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant


def _evisitor_payload(**overrides):
    base = {
        "enabled": True,
        "env": "test",
        "base_url": "https://www.evisitor.hr/testApi",
        "username": "user",
        "password": "secret",
        "api_key": "key",
        "facility_code": "12345",
    }
    base.update(overrides)
    return base


class EvisitorResolverTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
            default_language="hr",
        )
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="main",
            name="Main",
        )

    def _create_config(self, *, property=None, **payload):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.EVISITOR,
            property=property,
            is_active=True,
        )
        row.set_config_dict(_evisitor_payload(**payload))
        row.save()
        return row

    def test_raises_without_config(self):
        with self.assertRaises(EvisitorConfigError):
            resolve_evisitor_config(self.tenant, self.prop)

    def test_tenant_default_when_no_property_config(self):
        self._create_config(property=None, facility_code="TENANT")
        cfg = resolve_evisitor_config(self.tenant, self.prop)
        self.assertEqual(cfg.facility_code, "TENANT")

    def test_property_config_overrides_tenant_default(self):
        self._create_config(property=None, facility_code="TENANT")
        self._create_config(property=self.prop, facility_code="PROP")
        cfg = resolve_evisitor_config(self.tenant, self.prop)
        self.assertEqual(cfg.facility_code, "PROP")

    def test_property_times_override_integration_defaults(self):
        self._create_config(
            property=self.prop,
            default_stay_time_from="14:00",
            default_stay_time_until="10:00",
        )
        self.prop.check_in_time = time(15, 0)
        self.prop.check_out_time = time(11, 0)
        self.prop.save(update_fields=["check_in_time", "check_out_time"])
        cfg = resolve_evisitor_config(self.tenant, self.prop)
        self.assertEqual(cfg.default_stay_time_from, "15:00")
        self.assertEqual(cfg.default_stay_time_until, "11:00")

    def test_disabled_config_raises(self):
        self._create_config(property=self.prop, enabled=False)
        with self.assertRaises(EvisitorConfigError):
            resolve_evisitor_config(self.tenant, self.prop)

    def test_encrypted_roundtrip(self):
        row = self._create_config(property=self.prop)
        row.config = {}
        row.save(update_fields=["config"])
        decrypted = row.get_config_dict()
        self.assertEqual(decrypted["username"], "user")
        runtime = EvisitorRuntimeConfig.from_integration_dict(decrypted)
        self.assertTrue(runtime.enabled)
        self.assertEqual(runtime.api_key, "key")
