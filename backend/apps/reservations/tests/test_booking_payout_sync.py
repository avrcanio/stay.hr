from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from apps.billing.models import Invoice, TenantFiscalSettings
from apps.properties.models import Property
from apps.reservations.booking_payout.apply import apply_booking_payout_import
from apps.reservations.booking_payout.events import (
    BookingPayoutLineSynced,
    subscribe_booking_payout_line_synced,
)
from apps.reservations.booking_payout.preview import preview_booking_payout_csv
from apps.reservations.booking_payout.sync import (
    build_line_sync_preview,
    sync_booking_payout_import,
    sync_booking_payout_line,
)
from apps.reservations.booking_payout.types import BookingPayoutSyncErrorCode, SyncPolicy
from apps.reservations.booking_payout_models import (
    BookingPayoutImportStatus,
    BookingPayoutLine,
    BookingPayoutLineSyncResult,
    BookingPayoutMatchStatus,
)
from apps.reservations.models import Reservation, ReservationVersion, ReservationVersionScope
from apps.tenants.models import Tenant

User = get_user_model()

_PAYOUT_CSV = (
    "Type,Booking number,Check-in,Checkout,Guest name,Reservation status,"
    "Currency,Amount,Commission,Payments Service Fee,Net,Payout date,Payout ID\n"
    'Reservation,{booking_number},"Jun 1, 2026","Jun 5, 2026",John Doe,ok,EUR,'
    "{gross},{commission},{service_fee},{net},\"Jun 11, 2026\",{payout_id}\n"
)


def _csv_content(
    *,
    booking_number: str = "BP-1001",
    gross: str = "178.00",
    commission: str = "32.04",
    service_fee: str = "2.31",
    net: str = "143.65",
    payout_id: str = "PAY-SYNC-001",
) -> bytes:
    return _PAYOUT_CSV.format(
        booking_number=booking_number,
        gross=gross,
        commission=commission,
        service_fee=service_fee,
        net=net,
        payout_id=payout_id,
    ).encode("utf-8")


def _grant_sync_permission(user) -> None:
    content_type = ContentType.objects.get_for_model(BookingPayoutLine)
    perm = Permission.objects.get(
        codename="apply_booking_payout_line",
        content_type=content_type,
    )
    user.user_permissions.add(perm)


class BookingPayoutSyncTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Sync Tenant", slug="sync-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Sync Hotel",
            slug="sync-hotel",
        )
        self.user = User.objects.create_user(
            username="sync_user",
            password="test-pass-123",
            is_staff=True,
        )
        _grant_sync_permission(self.user)

        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BP-1001",
            external_id="BP-1001",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            booker_name="John Doe",
            amount=Decimal("178.00"),
            commission_amount=Decimal("34.35"),
            currency="EUR",
            import_source="booking_pdf",
            financial_source=Reservation.FinancialSource.BOOKING_PDF,
        )

        _preview, self.import_batch = preview_booking_payout_csv(
            _csv_content(),
            tenant=self.tenant,
            property_obj=self.property,
            filename="payout.csv",
            uploaded_by=self.user,
            persist=True,
        )
        assert self.import_batch is not None
        self.line = self.import_batch.lines.get(booking_number="BP-1001")


class BookingPayoutManualSyncTests(BookingPayoutSyncTestBase):
    def test_manual_override_updates_amounts_and_financial_source(self):
        result = sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )

        self.assertEqual(result.result, "SUCCESS")
        self.assertGreater(result.updated_fields_count, 0)

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.amount, Decimal("178.00"))
        self.assertEqual(self.reservation.commission_amount, Decimal("32.04"))
        self.assertEqual(
            self.reservation.financial_source,
            Reservation.FinancialSource.BOOKING_PAYOUT,
        )
        self.assertEqual(self.reservation.booking_payout_id, "PAY-SYNC-001")
        self.assertEqual(self.reservation.booking_payout_net, Decimal("143.65"))
        self.assertEqual(self.reservation.booking_payout_service_fee, Decimal("2.31"))

        self.line.refresh_from_db()
        self.assertIsNotNone(self.line.reservation_synced_at)
        self.assertEqual(self.line.last_sync_result, BookingPayoutLineSyncResult.SUCCESS)
        self.assertEqual(self.line.reservation_sync_reason, "booking_payout_override_pdf")
        self.assertIn("amount", self.line.reservation_before_sync)
        self.assertIn("amount", self.line.reservation_after_sync)

    def test_before_after_snapshot_json(self):
        sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.reservation_before_sync["commission_amount"], "34.35")
        self.assertEqual(self.line.reservation_after_sync["commission_amount"], "32.04")

    def test_no_changes_skips_version_touch(self):
        self.reservation.amount = Decimal("178.00")
        self.reservation.commission_amount = Decimal("32.04")
        self.reservation.booking_payout_id = "PAY-SYNC-001"
        self.reservation.booking_payout_net = Decimal("143.65")
        self.reservation.booking_payout_service_fee = Decimal("2.31")
        self.reservation.booking_payout_received_at = date(2026, 6, 11)
        self.reservation.booking_payout_line = self.line
        self.reservation.save()

        before_version = ReservationVersion.objects.filter(
            reservation=self.reservation,
            scope=ReservationVersionScope.PAYMENTS,
        ).first()

        result = sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )

        self.assertEqual(result.result, "NO_CHANGES")
        self.assertEqual(result.updated_fields_count, 0)

        after_version = ReservationVersion.objects.filter(
            reservation=self.reservation,
            scope=ReservationVersionScope.PAYMENTS,
        ).first()
        self.assertEqual(
            getattr(before_version, "version", None),
            getattr(after_version, "version", None),
        )

    def test_invoice_blocks_sync(self):
        TenantFiscalSettings.objects.create(tenant=self.tenant, is_vat_registered=True)
        Invoice.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            invoice_number="2026-001",
            sequence_number=1,
            issued_at=timezone.now(),
            buyer_name="John Doe",
            subtotal=Decimal("178.00"),
            vat_amount=Decimal("0.00"),
            total=Decimal("178.00"),
            currency="EUR",
        )

        result = sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )

        self.assertEqual(result.result, "FAILED")
        self.assertEqual(result.error_code, BookingPayoutSyncErrorCode.INVOICE_EXISTS)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.commission_amount, Decimal("34.35"))

    def test_payout_id_conflict(self):
        self.reservation.booking_payout_id = "OTHER-PAYOUT"
        self.reservation.save(update_fields=["booking_payout_id"])

        result = sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )

        self.assertEqual(result.result, "FAILED")
        self.assertEqual(result.error_code, BookingPayoutSyncErrorCode.PAYOUT_ID_CONFLICT)

    def test_stale_revision(self):
        sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )

        result = sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )
        self.assertEqual(result.result, "FAILED")
        self.assertEqual(result.error_code, BookingPayoutSyncErrorCode.STALE_REVISION)

    def test_permission_denied_without_perm(self):
        user = User.objects.create_user(username="no_perm", is_staff=True)
        result = sync_booking_payout_line(
            self.line.pk,
            applied_by=user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )
        self.assertEqual(result.result, "FAILED")
        self.assertEqual(result.error_code, BookingPayoutSyncErrorCode.PERMISSION_DENIED)

    def test_warnings_regenerated_not_merged(self):
        self.line.warnings = {"old_key": {"severity": "info", "message": "stale"}}
        self.line.save(update_fields=["warnings"])

        sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )

        self.line.refresh_from_db()
        self.assertNotIn("old_key", self.line.warnings)

    def test_event_emitted_on_success(self):
        events: list[BookingPayoutLineSynced] = []
        subscribe_booking_payout_line_synced(events.append)

        sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].line_id, self.line.pk)
        self.assertEqual(events[0].result, "SUCCESS")
        self.assertGreater(len(events[0].field_diffs), 0)

    def test_build_line_sync_preview(self):
        diffs = build_line_sync_preview(self.line, policy=SyncPolicy.MANUAL_OVERRIDE)
        fields = {d.field for d in diffs}
        self.assertIn("commission_amount", fields)
        commission_diff = next(d for d in diffs if d.field == "commission_amount")
        self.assertTrue(commission_diff.changed)


class BookingPayoutStateMachineTests(BookingPayoutSyncTestBase):
    def test_parsed_to_partially_synced_to_applied(self):
        line2_res = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BP-1002",
            external_id="BP-1002",
            check_in=date(2026, 6, 2),
            check_out=date(2026, 6, 6),
            booker_name="Jane Doe",
            amount=Decimal("100.00"),
            commission_amount=Decimal("15.00"),
            currency="EUR",
        )
        two_line_csv = (
            "Type,Booking number,Check-in,Checkout,Guest name,Reservation status,"
            "Currency,Amount,Commission,Payments Service Fee,Net,Payout date,Payout ID\n"
            'Reservation,BP-1001,"Jun 1, 2026","Jun 5, 2026",John Doe,ok,EUR,'
            '178.00,32.04,2.31,143.65,"Jun 11, 2026",PAY-SYNC-MULTI\n'
            'Reservation,BP-1002,"Jun 2, 2026","Jun 6, 2026",Jane Doe,ok,EUR,'
            '100.00,15.00,0.00,85.00,"Jun 11, 2026",PAY-SYNC-MULTI\n'
        ).encode("utf-8")
        _preview, import_batch = preview_booking_payout_csv(
            two_line_csv,
            tenant=self.tenant,
            property_obj=self.property,
            filename="payout_multi.csv",
            persist=True,
        )
        assert import_batch is not None
        line1 = import_batch.lines.get(booking_number="BP-1001")
        line2 = import_batch.lines.get(booking_number="BP-1002")
        line2.reservation = line2_res
        line2.match_status = BookingPayoutMatchStatus.MATCHED
        line2.save(update_fields=["reservation", "match_status"])

        self.assertEqual(import_batch.status, BookingPayoutImportStatus.PARSED)

        sync_booking_payout_line(
            line1.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=import_batch.revision,
        )
        import_batch.refresh_from_db()
        self.assertEqual(import_batch.status, BookingPayoutImportStatus.PARTIALLY_SYNCED)

        sync_booking_payout_line(
            line2.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=import_batch.revision,
        )
        import_batch.refresh_from_db()
        self.assertEqual(import_batch.status, BookingPayoutImportStatus.APPLIED)

    def test_reconciliation_health_pct(self):
        self.assertEqual(self.import_batch.reconciliation_health_pct, 0)

        sync_booking_payout_line(
            self.line.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )
        self.import_batch.refresh_from_db()
        self.assertEqual(self.import_batch.synced_lines_count, 1)
        self.assertEqual(self.import_batch.reconciliation_health_pct, 100)


class BookingPayoutSafeApplyTests(BookingPayoutSyncTestBase):
    def test_safe_apply_does_not_change_amounts(self):
        result = apply_booking_payout_import(self.import_batch.pk, applied_by=self.user)

        self.assertEqual(result.applied, 1)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.commission_amount, Decimal("34.35"))
        self.assertEqual(self.reservation.booking_payout_id, "PAY-SYNC-001")

        self.import_batch.refresh_from_db()
        self.assertEqual(self.import_batch.status, BookingPayoutImportStatus.APPLIED)

    def test_bulk_manual_override(self):
        result = sync_booking_payout_import(
            self.import_batch.pk,
            applied_by=self.user,
            policy=SyncPolicy.MANUAL_OVERRIDE,
            expected_revision=self.import_batch.revision,
        )
        self.assertEqual(result.success, 1)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.commission_amount, Decimal("32.04"))


@override_settings(ALLOWED_HOSTS=["admin.stay.hr", "testserver"])
class BookingPayoutAdminSyncTests(BookingPayoutSyncTestBase):
    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(
            username="admin_sync",
            password="test-pass-123",
            email="admin@sync.test",
        )
        _grant_sync_permission(self.superuser)
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_confirm_page_shows_field_diffs(self):
        url = reverse(
            "admin:reservations_bookingpayoutimport_sync_line",
            args=[self.import_batch.pk, self.line.pk],
        )
        response = self.client.get(url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "commission_amount")
        self.assertContains(response, "34.35")
        self.assertContains(response, "32.04")
        self.assertContains(response, "Potvrdi sync")

    def test_confirm_post_syncs_line(self):
        url = reverse(
            "admin:reservations_bookingpayoutimport_sync_line",
            args=[self.import_batch.pk, self.line.pk],
        )
        response = self.client.post(
            url,
            {"revision": self.import_batch.revision},
            HTTP_HOST="admin.stay.hr",
        )
        self.assertEqual(response.status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.commission_amount, Decimal("32.04"))

    def test_change_form_shows_reconciliation_health(self):
        url = reverse(
            "admin:reservations_bookingpayoutimport_change",
            args=[self.import_batch.pk],
        )
        response = self.client.get(url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reconciliation")
