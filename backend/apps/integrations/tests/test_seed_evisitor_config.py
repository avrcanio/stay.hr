from __future__ import annotations

import io
import os
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.integrations.evisitor.resolver import resolve_evisitor_config
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="

_FULL_ENV = {
    "DEMO_EVISITOR_USERNAME": "demo-user",
    "DEMO_EVISITOR_PASSWORD": "demo-pass",
    "DEMO_EVISITOR_API_KEY": "demo-key",
    "DEMO_EVISITOR_FACILITY_CODE": "123456",
    "DEMO_EVISITOR_BASE_URL": "https://www.evisitor.hr/testApi",
    "DEMO_EVISITOR_ENV": "test",
    "DEMO_EVISITOR_ENABLED": "true",
}


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class SeedEvisitorConfigCommandTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="demo",
            name="Demo",
            timezone="Europe/Zagreb",
            default_language="hr",
        )
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="demo",
            name="Demo Property",
        )

    def test_missing_required_env_exits_without_row(self):
        env = {k: v for k, v in _FULL_ENV.items() if k != "DEMO_EVISITOR_USERNAME"}
        with patch.dict(os.environ, env, clear=False):
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                call_command("seed_evisitor_config", stderr=stderr)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(IntegrationConfig.objects.count(), 0)
        self.assertIn("DEMO_EVISITOR_USERNAME", stderr.getvalue())

    def test_missing_api_key_on_test_env(self):
        env = {k: v for k, v in _FULL_ENV.items() if k != "DEMO_EVISITOR_API_KEY"}
        with patch.dict(os.environ, env, clear=False):
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                call_command("seed_evisitor_config", stderr=stderr)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(IntegrationConfig.objects.count(), 0)
        self.assertIn("DEMO_EVISITOR_API_KEY", stderr.getvalue())

    def test_property_not_found_exits_1(self):
        with patch.dict(os.environ, _FULL_ENV, clear=False):
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                call_command(
                    "seed_evisitor_config",
                    property_slug="missing",
                    stderr=stderr,
                )
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(IntegrationConfig.objects.count(), 0)
        self.assertIn("Property 'missing' not found", stderr.getvalue())

    def test_creates_property_level_config(self):
        with patch.dict(os.environ, _FULL_ENV, clear=False):
            stdout = io.StringIO()
            call_command("seed_evisitor_config", stdout=stdout)

        self.assertEqual(IntegrationConfig.objects.count(), 1)
        row = IntegrationConfig.objects.get()
        self.assertEqual(row.property_id, self.prop.pk)
        self.assertEqual(row.provider, IntegrationConfig.Provider.EVISITOR)
        self.assertTrue(row.is_active)

        output = stdout.getvalue()
        self.assertIn("Created eVisitor IntegrationConfig", output)
        self.assertIn("Created: yes", output)
        self.assertIn("Scope: property/demo/demo", output)
        self.assertIn("Facility: 123456", output)

        row.refresh_from_db()
        self.assertEqual(row.config, {})
        self.assertTrue(row.config_encrypted)
        decrypted = row.get_config_dict()
        self.assertEqual(decrypted["username"], "demo-user")
        self.assertEqual(decrypted["password"], "demo-pass")
        self.assertEqual(decrypted["api_key"], "demo-key")
        self.assertNotIn("demo-pass", row.config_encrypted)

    def test_tenant_level_flag(self):
        with patch.dict(os.environ, _FULL_ENV, clear=False):
            call_command("seed_evisitor_config", tenant_level=True)

        row = IntegrationConfig.objects.get()
        self.assertIsNone(row.property_id)

    def test_idempotent_update(self):
        with patch.dict(os.environ, _FULL_ENV, clear=False):
            stdout1 = io.StringIO()
            call_command("seed_evisitor_config", stdout=stdout1)
            pk = IntegrationConfig.objects.get().pk

            updated_env = {**_FULL_ENV, "DEMO_EVISITOR_FACILITY_CODE": "999888"}
            with patch.dict(os.environ, updated_env, clear=False):
                stdout2 = io.StringIO()
                call_command("seed_evisitor_config", stdout=stdout2)

        self.assertEqual(IntegrationConfig.objects.count(), 1)
        self.assertEqual(IntegrationConfig.objects.get().pk, pk)
        self.assertEqual(
            IntegrationConfig.objects.get().get_config_dict()["facility_code"],
            "999888",
        )
        self.assertIn("Updated eVisitor IntegrationConfig", stdout2.getvalue())
        self.assertIn("Created: no", stdout2.getvalue())

    def test_enabled_parser_tolerant(self):
        for raw in ("YES", "1", "on"):
            IntegrationConfig.objects.all().delete()
            env = {**_FULL_ENV, "DEMO_EVISITOR_ENABLED": raw}
            with patch.dict(os.environ, env, clear=False):
                call_command("seed_evisitor_config")
            self.assertTrue(
                IntegrationConfig.objects.get().get_config_dict()["enabled"]
            )

        IntegrationConfig.objects.all().delete()
        env = {**_FULL_ENV, "DEMO_EVISITOR_ENABLED": "OFF"}
        with patch.dict(os.environ, env, clear=False):
            call_command("seed_evisitor_config")
        self.assertFalse(
            IntegrationConfig.objects.get().get_config_dict()["enabled"]
        )

    def test_enabled_parser_invalid_exits_1(self):
        env = {**_FULL_ENV, "DEMO_EVISITOR_ENABLED": "treu"}
        with patch.dict(os.environ, env, clear=False):
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                call_command("seed_evisitor_config", stderr=stderr)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(IntegrationConfig.objects.count(), 0)
        stderr_text = stderr.getvalue()
        self.assertIn('Invalid value for DEMO_EVISITOR_ENABLED: "treu"', stderr_text)
        self.assertIn("true, false, 1, 0, yes, no, on, off", stderr_text)

    def test_resolve_after_seed(self):
        with patch.dict(os.environ, _FULL_ENV, clear=False):
            call_command("seed_evisitor_config")

        config = resolve_evisitor_config(self.tenant, self.prop)
        self.assertEqual(config.facility_code, "123456")
        self.assertEqual(config.env, "test")
        self.assertTrue(config.enabled)
