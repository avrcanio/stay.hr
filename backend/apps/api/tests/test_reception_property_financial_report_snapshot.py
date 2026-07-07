import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "property_financial_report_snapshot.json"
)
SNAPSHOT_GENERATED_AT = datetime(2026, 4, 1, 8, 30, 0, tzinfo=ZoneInfo("Europe/Zagreb"))


class PropertyFinancialReportResponseSnapshotTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita Luxury Rooms",
            slug="uzorita",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="101",
            name="Soba 101",
            is_active=True,
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Snapshot tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}
        self.url = "/api/v1/reception/reports/property-financial/"

        self.complete = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-COMPLETE",
            external_id="ext-complete",
            check_in=date(2026, 3, 10),
            check_out=date(2026, 3, 13),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Ana Anić",
            amount=Decimal("150.00"),
            commission_amount=Decimal("15.00"),
            nights_count=3,
            currency="EUR",
            source="booking.com",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.complete,
            unit=self.unit,
            sort_order=0,
            room_name="Soba 101",
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.complete,
            first_name="Ana",
            last_name="Anić",
            nationality="HR",
            is_primary=True,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.complete,
            first_name="Petra",
            last_name="Petrović",
            nationality="DE",
            is_primary=False,
        )

        self.no_commission = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-NO-COMM",
            external_id="ext-no-comm",
            check_in=date(2026, 3, 20),
            check_out=date(2026, 3, 22),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Marko Marković",
            amount=Decimal("80.00"),
            commission_amount=None,
            nights_count=2,
            currency="EUR",
            source="direct",
        )

    @patch("apps.reservations.reports.property_financial_report.timezone.now")
    def test_full_report_response_snapshot(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            SNAPSHOT_GENERATED_AT.replace(tzinfo=None),
            SNAPSHOT_GENERATED_AT.tzinfo,
        )

        response = self.client.get(
            self.url,
            {
                "property_slug": "uzorita",
                "check_out_from": "2026-03-01",
                "check_out_to": "2026-03-31",
            },
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        expected = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        ids_by_code = {
            "BK-COMPLETE": self.complete.id,
            "BK-NO-COMM": self.no_commission.id,
        }
        for row in expected["rows"]:
            row["reservation_id"] = ids_by_code[row["booking_code"]]
        self.assertEqual(response.json(), expected)
