from __future__ import annotations

import io
import json
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.integrations.evisitor.exceptions import EvisitorApiError
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.reservations.models import EvisitorGuestStatus, EvisitorSubmission, Guest, Reservation
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


class SmokeEvisitorCommandTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="demo",
            name="Demo",
            timezone="Europe/Zagreb",
            default_language="hr",
        )
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="main",
            name="Main",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.prop,
            booker_name="Test Guest",
            check_in=date(2026, 6, 11),
            check_out=date(2026, 6, 13),
            status=Reservation.Status.EXPECTED,
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

    def _complete_guest(self, **kwargs) -> Guest:
        defaults = {
            "tenant": self.tenant,
            "reservation": self.reservation,
            "first_name": "Test",
            "last_name": "Guest",
            "name": "Test Guest",
            "sex": "M",
            "date_of_birth": date(1990, 1, 1),
            "nationality": "DE",
            "document_type": "national_id",
            "document_number": "L1234567",
            "document_country_iso2": "DE",
            "document_country_iso3": "DEU",
            "address": "Berlin, Grad Berlin",
        }
        defaults.update(kwargs)
        return Guest.objects.create(**defaults)

    def test_missing_config_exits_1(self):
        with self.assertRaises(SystemExit) as ctx:
            call_command("smoke_evisitor", tenant_slug="demo", stderr=io.StringIO())
        self.assertEqual(ctx.exception.code, 1)

    def test_list_config_human(self):
        row = self._create_config(property=self.prop, facility_code="PROP")
        stderr = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            list_config=True,
            stderr=stderr,
        )
        output = stderr.getvalue()
        self.assertIn("Scope: property/demo/main", output)
        self.assertIn(f"Row ID: {row.pk}", output)
        self.assertIn("SMOKE PASSED", output)

    def test_list_config_json(self):
        self._create_config(property=self.prop)
        stdout = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            list_config=True,
            json=True,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["config_scope"]["level"], "property")
        self.assertEqual(payload["config_scope"]["property_slug"], "main")
        self.assertTrue(payload["steps"]["config"])
        self.assertNotIn("password", stdout.getvalue())
        self.assertNotIn("api_key", stdout.getvalue())

    def test_list_config_property_override(self):
        self._create_config(property=None, facility_code="TENANT")
        self._create_config(property=self.prop, facility_code="PROP")
        stderr = io.StringIO()
        stdout = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            list_config=True,
            stderr=stderr,
            stdout=stdout,
        )
        self.assertIn("Scope: property/demo/main", stderr.getvalue())
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            list_config=True,
            json=True,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["config_scope"]["level"], "property")
        self.assertEqual(payload["config_scope"]["property_slug"], "main")
        self.assertEqual(payload["facility_code"], "PROP")

    @patch("apps.integrations.management.commands.smoke_evisitor.EvisitorClient")
    def test_login_only_json(self, mock_client_cls):
        self._create_config(property=self.prop)
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        stdout = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            login_only=True,
            json=True,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["exit_code"], 0)
        self.assertTrue(payload["steps"]["config"])
        self.assertTrue(payload["steps"]["login"])
        self.assertFalse(payload["steps"]["submit"])

    @patch("apps.integrations.management.commands.smoke_evisitor.EvisitorClient")
    def test_login_only_success(self, mock_client_cls):
        self._create_config(property=self.prop)
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        stderr = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            login_only=True,
            stderr=stderr,
        )
        mock_client.login.assert_called_once()
        mock_client.logout.assert_called_once()
        mock_client.close.assert_called_once()
        self.assertIn("SMOKE PASSED", stderr.getvalue())

    @patch("apps.integrations.management.commands.smoke_evisitor.EvisitorClient")
    def test_login_failed_exits_2(self, mock_client_cls):
        self._create_config(property=self.prop)
        mock_client = MagicMock()
        mock_client.login.side_effect = EvisitorApiError("eVisitor login nije uspio")
        mock_client_cls.return_value = mock_client

        stderr = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "smoke_evisitor",
                tenant_slug="demo",
                property_slug="main",
                login_only=True,
                stderr=stderr,
            )
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("Login Failed", stderr.getvalue())

    @patch("apps.integrations.management.commands.smoke_evisitor.EvisitorClient")
    @patch("apps.integrations.evisitor.mapper.iso2_to_iso3", return_value="DEU")
    def test_dry_run_validation_failed_exits_3(self, _mock_iso, mock_client_cls):
        self._create_config(property=self.prop)
        guest = self._complete_guest(first_name="", last_name="Guest")
        mock_client_cls.return_value = MagicMock()

        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "smoke_evisitor",
                tenant_slug="demo",
                property_slug="main",
                guest_id=guest.pk,
                dry_run=True,
                json=True,
                stdout=stdout,
            )
        self.assertEqual(ctx.exception.code, 3)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["reason"], "validation_failed")
        self.assertIn("first_name", payload["field_errors"])

    @patch("apps.integrations.management.commands.smoke_evisitor.EvisitorClient")
    @patch("apps.integrations.evisitor.mapper.iso2_to_iso3", return_value="DEU")
    def test_dry_run_valid_payload_exits_0(self, _mock_iso, mock_client_cls):
        self._create_config(property=self.prop)
        guest = self._complete_guest()
        mock_client_cls.return_value = MagicMock()

        stdout = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            guest_id=guest.pk,
            dry_run=True,
            json=True,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["steps"]["payload"])
        self.assertFalse(payload["steps"]["submit"])

    @patch("apps.integrations.management.commands.smoke_evisitor.submit_guest_checkin")
    @patch("apps.integrations.management.commands.smoke_evisitor.EvisitorClient")
    def test_submit_already_sent_passes(self, mock_client_cls, mock_submit):
        self._create_config(property=self.prop)
        guest = self._complete_guest(evisitor_status=EvisitorGuestStatus.SENT)
        submission = EvisitorSubmission.objects.create(
            tenant=self.tenant,
            guest=guest,
            registration_id=uuid4(),
            status=EvisitorGuestStatus.SENT,
            created_at=timezone.now(),
        )
        mock_submit.return_value = submission
        mock_client_cls.return_value = MagicMock()

        stdout = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            guest_id=guest.pk,
            json=True,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["submit_skipped_reason"], "already_sent")
        self.assertFalse(payload["steps"]["submit"])

    @patch("apps.integrations.management.commands.smoke_evisitor.submit_guest_checkin")
    @patch("apps.integrations.management.commands.smoke_evisitor.EvisitorClient")
    def test_submit_recovered_passes(self, mock_client_cls, mock_submit):
        self._create_config(property=self.prop)
        guest = self._complete_guest()
        submission = EvisitorSubmission.objects.create(
            tenant=self.tenant,
            guest=guest,
            registration_id=uuid4(),
            status=EvisitorGuestStatus.SENT,
            response_payload={"ok": True, "recovered": True},
            created_at=timezone.now(),
        )
        mock_submit.return_value = submission
        mock_client_cls.return_value = MagicMock()

        stdout = io.StringIO()
        call_command(
            "smoke_evisitor",
            tenant_slug="demo",
            property_slug="main",
            guest_id=guest.pk,
            json=True,
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["recovered"])
        self.assertTrue(payload["steps"]["submit"])

    def test_conflicting_flags(self):
        self._create_config(property=self.prop)
        guest = self._complete_guest()
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "smoke_evisitor",
                tenant_slug="demo",
                guest_id=guest.pk,
                login_only=True,
                stderr=io.StringIO(),
            )
        self.assertEqual(ctx.exception.code, 1)

        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "smoke_evisitor",
                tenant_slug="demo",
                dry_run=True,
                stderr=io.StringIO(),
            )
        self.assertEqual(ctx.exception.code, 1)
