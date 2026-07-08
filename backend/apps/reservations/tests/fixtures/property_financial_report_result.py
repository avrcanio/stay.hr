"""Build PropertyFinancialReportResult fixtures for export unit tests (no DB)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from apps.reservations.reports.types import (
    PayoutStatus,
    PropertyFinancialReportGuestRow,
    PropertyFinancialReportMeta,
    PropertyFinancialReportResult,
    PropertyFinancialReportRow,
    PropertyFinancialReportTotals,
)


def sample_property_financial_report_result() -> PropertyFinancialReportResult:
    return PropertyFinancialReportResult(
        meta=PropertyFinancialReportMeta(
            property_name="Uzorita Luxury Rooms",
            property_slug="uzorita",
            check_out_from=date(2026, 3, 1),
            check_out_to=date(2026, 3, 31),
            generated_at=datetime(2026, 4, 1, 8, 30, 0, tzinfo=ZoneInfo("Europe/Zagreb")),
            currency="EUR",
            max_period_days=90,
            rows_with_missing_commission=1,
            rows_without_confirmed_payout=1,
        ),
        rows=(
            PropertyFinancialReportRow(
                reservation_id=101,
                booking_code="BK-COMPLETE",
                external_id="ext-complete",
                check_in=date(2026, 3, 10),
                check_out=date(2026, 3, 13),
                status="checked_out",
                room_labels=("Soba 101",),
                nights=3,
                gross=Decimal("150.00"),
                commission=Decimal("15.00"),
                net=Decimal("135.00"),
                currency="EUR",
                source="booking.com",
                guests=(
                    PropertyFinancialReportGuestRow(
                        name="Ana Anić",
                        nationality_iso2="HR",
                        is_primary=True,
                    ),
                    PropertyFinancialReportGuestRow(
                        name="Petra Petrović",
                        nationality_iso2="DE",
                        is_primary=False,
                    ),
                ),
                payout_status=PayoutStatus.NOT_PAID,
                payout_received_at=None,
                paid_amount=None,
            ),
            PropertyFinancialReportRow(
                reservation_id=102,
                booking_code="BK-NO-COMM",
                external_id="ext-no-comm",
                check_in=date(2026, 3, 20),
                check_out=date(2026, 3, 22),
                status="checked_out",
                room_labels=(),
                nights=2,
                gross=Decimal("80.00"),
                commission=None,
                net=None,
                currency="EUR",
                source="direct",
                guests=(),
                payout_status=PayoutStatus.NOT_APPLICABLE,
                payout_received_at=None,
                paid_amount=None,
            ),
        ),
        totals=PropertyFinancialReportTotals(
            reservation_count=2,
            nights=5,
            gross=Decimal("230.00"),
            commission=Decimal("15.00"),
            net=Decimal("135.00"),
        ),
    )
