from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant

LEGACY_XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class BookingReconcileAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}
        self.compare_url = "/api/v1/reception/reports/booking-reconcile/compare/"
        self.apply_url = "/api/v1/reception/reports/booking-reconcile/apply/"

    def _xls_upload(self, *, name: str = "export.xls", content: bytes | None = None):
        payload = content if content is not None else LEGACY_XLS_SIGNATURE + b"fake"
        return BytesIO(payload)

    def test_compare_requires_auth(self):
        response = self.client.post(
            self.compare_url,
            {"property_slug": "uzorita", "file": self._xls_upload()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)

    def test_compare_invalid_file(self):
        response = self.client.post(
            self.compare_url,
            {
                "property_slug": "uzorita",
                "file": ("bad.xlsx", BytesIO(b"not-xls"), "application/octet-stream"),
            },
            format="multipart",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_file")

    @patch("apps.api.reception_booking_reconcile_views.compare_booking_export")
    def test_compare_success_shape(self, mock_compare):
        from apps.reservations.reports.booking_reconcile_types import (
            BookingReconcileMeta,
            BookingReconcileResult,
            BookingReconcileRow,
            BookingReconcileMatchKind,
            summarize_booking_reconcile_rows,
        )

        rows = (
            BookingReconcileRow(
                row_key="1:123",
                booking_code="123",
                booking_external_id="123",
                match_kind=BookingReconcileMatchKind.MATCHED,
                reservation_id=1,
                guest_name="Ana",
                booking_status="ok",
                stay_status="checked_out",
                booking_amount=Decimal("100.00"),
                stay_amount=Decimal("100.00"),
                booking_commission=Decimal("10.00"),
                stay_commission=None,
                check_in=date(2026, 6, 1),
                check_out=date(2026, 6, 3),
                differences=(),
            ),
        )
        meta = BookingReconcileMeta(
            tenant_id=self.tenant.id,
            property_id=self.property.id,
            property_slug="uzorita",
            filename="export.xls",
            date_axis="check_out",
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            generated_at=timezone.now(),
            parser_version="booking_xls_import.v1",
        )
        mock_compare.return_value = BookingReconcileResult(
            snapshot_id="11111111-1111-1111-1111-111111111111",
            meta=meta,
            summary=summarize_booking_reconcile_rows(rows),
            rows=rows,
        )

        response = self.client.post(
            self.compare_url,
            {
                "property_slug": "uzorita",
                "date_axis": "check_out",
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "file": ("export.xls", self._xls_upload(), "application/vnd.ms-excel"),
            },
            format="multipart",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["snapshot_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(data["meta"]["property_slug"], "uzorita")
        self.assertEqual(data["summary"]["matched"], 1)
        self.assertEqual(len(data["rows"]), 1)

    @patch("apps.api.reception_booking_reconcile_views.apply_booking_reconcile_fixes")
    def test_apply_fill_empty(self, mock_apply):
        from apps.reservations.reports.booking_reconcile_apply import BookingReconcileApplyRowResult

        mock_apply.return_value = (
            BookingReconcileApplyRowResult(
                booking_code="123",
                applied=True,
                skipped=False,
                reason="applied",
                reservation_id=99,
            ),
        )

        response = self.client.post(
            self.apply_url,
            {
                "snapshot_id": "11111111-1111-1111-1111-111111111111",
                "property_slug": "uzorita",
                "mode": "fill_empty",
                "items": [{"booking_code": "123", "fields": ["commission_amount"]}],
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["results"][0]["applied"])

    @patch("apps.api.reception_booking_reconcile_views.apply_booking_reconcile_fixes")
    def test_apply_pdf_locked(self, mock_apply):
        from apps.reservations.reports.booking_reconcile_apply import BookingReconcileApplyRowResult

        mock_apply.return_value = (
            BookingReconcileApplyRowResult(
                booking_code="123",
                applied=False,
                skipped=True,
                reason="pdf_locked",
                reservation_id=99,
            ),
        )

        response = self.client.post(
            self.apply_url,
            {
                "snapshot_id": "11111111-1111-1111-1111-111111111111",
                "property_slug": "uzorita",
                "mode": "fill_empty",
                "items": [{"booking_code": "123", "fields": ["commission_amount"]}],
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["reason"], "pdf_locked")

    @patch("apps.api.reception_booking_reconcile_views.recompare_from_snapshot")
    def test_recompare_from_snapshot(self, mock_recompare):
        from apps.reservations.reports.booking_reconcile_types import (
            BookingReconcileMeta,
            BookingReconcileResult,
            BookingReconcileSummary,
        )

        mock_recompare.return_value = BookingReconcileResult(
            snapshot_id="22222222-2222-2222-2222-222222222222",
            meta=BookingReconcileMeta(
                tenant_id=self.tenant.id,
                property_id=self.property.id,
                property_slug="uzorita",
                filename="export.xls",
                date_axis="check_out",
                date_from=date(2026, 6, 1),
                date_to=date(2026, 6, 30),
                generated_at=timezone.now(),
                parser_version="booking_xls_import.v1",
            ),
            summary=BookingReconcileSummary(
                total_rows=1,
                matched=1,
                missing_in_stay=0,
                missing_in_booking=0,
                parse_errors=0,
                rows_with_differences=0,
                fixable_rows=0,
                booking_total_amount=Decimal("100"),
                stay_total_amount=Decimal("100"),
                booking_total_commission=Decimal("10"),
                stay_total_commission=Decimal("10"),
            ),
            rows=(),
        )

        response = self.client.post(
            "/api/v1/reception/reports/booking-reconcile/recompare/",
            {
                "snapshot_id": "11111111-1111-1111-1111-111111111111",
                "property_slug": "uzorita",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["snapshot_id"],
            "22222222-2222-2222-2222-222222222222",
        )
