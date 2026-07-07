"""Lifecycle gate for WhatsApp document intake automation."""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.integrations.whatsapp.apply_reply import waive_whatsapp_autocheckin
from apps.integrations.whatsapp.guest_document_lifecycle import (
    LifecycleBlockReason,
    check_guest_document_intake_automation,
    guest_document_intake_automation_allowed,
)
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

BACKEND_ROOT = Path(__file__).resolve().parents[2]
INTEGRATIONS_WHATSAPP = BACKEND_ROOT / "apps" / "integrations" / "whatsapp"

LIFECYCLE_CALLER_FILES = (
    INTEGRATIONS_WHATSAPP / "whatsapp_document_batch.py",
    INTEGRATIONS_WHATSAPP / "document_intake_finalize.py",
)

FORBIDDEN_LIFECYCLE_GUARD_CALLS = frozenset(
    {
        "is_whatsapp_autocheckin_waived",
        "is_document_checkin_complete",
    }
)

GATE_MODULE = INTEGRATIONS_WHATSAPP / "guest_document_lifecycle.py"

FORBIDDEN_GATE_SIDE_EFFECTS = frozenset(
    {
        "save",
        "create",
        "update",
        "delete",
        "send_text_message",
        "send_interactive_button_message",
        "send_guest_message",
    }
)


class GuestDocumentLifecycleGateTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo", name="Demo", default_language="hr")
        self.property = Property.objects.create(tenant=self.tenant, name="Demo Hotel", slug="demo")
        today = timezone.localdate()
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ana Anić",
            booker_phone="+385911234567",
            adults_count=2,
            check_in=today,
            check_out=today + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
        )

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    def test_expected_reservation_allowed(self):
        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertTrue(allowed)
        self.assertEqual(reason, LifecycleBlockReason.ALLOWED)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    def test_waived_blocks_automation(self):
        waive_whatsapp_autocheckin(self.reservation)
        self.reservation.refresh_from_db()

        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.WAIVED)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    @patch(
        "apps.integrations.whatsapp.guest_document_lifecycle.is_document_checkin_complete",
        return_value=True,
    )
    def test_documents_complete_blocks_automation(self, _mock_complete):
        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.DOCUMENTS_COMPLETE)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    def test_checked_out_blocks_automation(self):
        self.reservation.status = Reservation.Status.CHECKED_OUT
        self.reservation.save(update_fields=["status", "updated_at"])

        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.CHECKED_OUT)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    def test_canceled_blocks_automation(self):
        self.reservation.status = Reservation.Status.CANCELED
        self.reservation.save(update_fields=["status", "updated_at"])

        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.CANCELED)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    def test_no_show_blocks_automation(self):
        self.reservation.status = Reservation.Status.NO_SHOW
        self.reservation.save(update_fields=["status", "updated_at"])

        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.NO_SHOW)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    def test_refused_blocks_automation(self):
        self.reservation.status = Reservation.Status.REFUSED
        self.reservation.save(update_fields=["status", "updated_at"])

        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.REFUSED)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=False)
    def test_flag_off_terminal_status_allowed(self):
        self.reservation.status = Reservation.Status.CHECKED_OUT
        self.reservation.save(update_fields=["status", "updated_at"])

        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertTrue(allowed)
        self.assertEqual(reason, LifecycleBlockReason.ALLOWED)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=False)
    def test_flag_off_waived_still_blocks(self):
        waive_whatsapp_autocheckin(self.reservation)
        self.reservation.refresh_from_db()

        allowed, reason = guest_document_intake_automation_allowed(self.reservation)
        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.WAIVED)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    @patch(
        "apps.integrations.whatsapp.guest_document_lifecycle.is_document_checkin_complete",
        return_value=True,
    )
    def test_block_documents_complete_can_be_disabled(self, _mock_complete):
        allowed, reason = guest_document_intake_automation_allowed(
            self.reservation,
            block_documents_complete=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, LifecycleBlockReason.ALLOWED)

    @override_settings(WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=True)
    def test_check_logs_automation_blocked(self):
        self.reservation.status = Reservation.Status.CHECKED_OUT
        self.reservation.save(update_fields=["status", "updated_at"])

        with self.assertLogs(
            "apps.integrations.whatsapp.guest_document_lifecycle",
            level="INFO",
        ) as logs:
            allowed, reason = check_guest_document_intake_automation(self.reservation)

        self.assertFalse(allowed)
        self.assertEqual(reason, LifecycleBlockReason.CHECKED_OUT)
        self.assertTrue(
            any(
                "automation_blocked reservation_id="
                f"{self.reservation.pk} reason=checked_out" in line
                for line in logs.output
            )
        )


def _collect_call_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
            self.generic_visit(node)

    Visitor().visit(tree)
    return names


class GuestDocumentLifecycleArchTests(TestCase):
    def test_lifecycle_callers_do_not_use_inline_guards(self):
        violations: list[str] = []
        for path in LIFECYCLE_CALLER_FILES:
            source = path.read_text(encoding="utf-8")
            calls = _collect_call_names(source)
            forbidden = calls & FORBIDDEN_LIFECYCLE_GUARD_CALLS
            if forbidden:
                violations.append(f"{path.name}: {sorted(forbidden)}")
        self.assertEqual(violations, [])

    def test_gate_module_has_no_side_effect_calls(self):
        source = GATE_MODULE.read_text(encoding="utf-8")
        calls = _collect_call_names(source)
        forbidden = calls & FORBIDDEN_GATE_SIDE_EFFECTS
        self.assertEqual(
            forbidden,
            set(),
            msg=f"guest_document_lifecycle.py must stay read-only; found: {sorted(forbidden)}",
        )
