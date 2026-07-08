"""Frozen contract for Booking.com XLS reconcile (compare + apply)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from apps.properties.models import Property
from apps.tenants.models import Tenant

BookingReconcileValue = Decimal | str | date | int | None

PARSER_VERSION = "booking_xls_import.v1"


class BookingReconcileMatchKind(StrEnum):
    MATCHED = "matched"
    MISSING_IN_STAY = "missing_in_stay"
    MISSING_IN_BOOKING = "missing_in_booking"
    PARSE_ERROR = "parse_error"


class BookingDiffSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class BookingReconcileBlockReason(StrEnum):
    PDF_LOCKED = "pdf_locked"
    STALE_XLS = "stale_xls"
    STATUS_PROTECTED = "status_protected"


class BookingFieldKey(StrEnum):
    AMOUNT = "amount"
    COMMISSION_AMOUNT = "commission_amount"
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    STATUS = "status"
    UNITS_COUNT = "units_count"


FIELD_LABELS: dict[BookingFieldKey, str] = {
    BookingFieldKey.AMOUNT: "Gross amount",
    BookingFieldKey.COMMISSION_AMOUNT: "Commission",
    BookingFieldKey.CHECK_IN: "Check-in",
    BookingFieldKey.CHECK_OUT: "Check-out",
    BookingFieldKey.STATUS: "Status",
    BookingFieldKey.UNITS_COUNT: "Units",
}


@dataclass(frozen=True)
class BookingFieldDiff:
    field_key: BookingFieldKey
    field_label: str
    booking_value: BookingReconcileValue
    stay_value: BookingReconcileValue
    booking_display: str
    stay_display: str
    severity: BookingDiffSeverity
    fixable: bool
    block_reasons: tuple[BookingReconcileBlockReason, ...]


@dataclass(frozen=True)
class BookingReconcileRow:
    row_key: str
    booking_code: str
    booking_external_id: str
    match_kind: BookingReconcileMatchKind

    reservation_id: int | None
    guest_name: str

    booking_status: str
    stay_status: str | None

    booking_amount: Decimal | None
    stay_amount: Decimal | None
    booking_commission: Decimal | None
    stay_commission: Decimal | None
    check_in: date | None
    check_out: date | None

    differences: tuple[BookingFieldDiff, ...]
    parse_error: str | None = None

    @property
    def has_differences(self) -> bool:
        return bool(self.differences)

    @property
    def is_fixable(self) -> bool:
        if self.match_kind is BookingReconcileMatchKind.MISSING_IN_STAY:
            return True
        return any(d.fixable for d in self.differences)


@dataclass(frozen=True)
class BookingReconcileSummary:
    total_rows: int
    matched: int
    missing_in_stay: int
    missing_in_booking: int
    parse_errors: int
    rows_with_differences: int
    fixable_rows: int
    booking_total_amount: Decimal
    stay_total_amount: Decimal
    booking_total_commission: Decimal
    stay_total_commission: Decimal


@dataclass(frozen=True)
class BookingReconcileMeta:
    tenant_id: int
    property_id: int
    property_slug: str
    filename: str
    date_axis: Literal["check_out", "check_in"] | None
    date_from: date | None
    date_to: date | None
    generated_at: datetime
    parser_version: str


@dataclass(frozen=True)
class BookingReconcileResult:
    snapshot_id: str | None
    meta: BookingReconcileMeta
    summary: BookingReconcileSummary
    rows: tuple[BookingReconcileRow, ...]

    @property
    def rows_with_differences(self) -> tuple[BookingReconcileRow, ...]:
        return tuple(r for r in self.rows if r.has_differences)

    @property
    def fixable_rows(self) -> tuple[BookingReconcileRow, ...]:
        return tuple(r for r in self.rows if r.is_fixable)


@dataclass(frozen=True)
class BookingReconcileParams:
    tenant: Tenant
    property: Property
    date_axis: Literal["check_out", "check_in"] | None
    date_from: date | None
    date_to_inclusive: date | None
    filename: str


def summarize_booking_reconcile_rows(
    rows: tuple[BookingReconcileRow, ...],
) -> BookingReconcileSummary:
    matched = 0
    missing_in_stay = 0
    missing_in_booking = 0
    parse_errors = 0
    rows_with_differences = 0
    fixable_rows = 0
    booking_total_amount = Decimal("0")
    stay_total_amount = Decimal("0")
    booking_total_commission = Decimal("0")
    stay_total_commission = Decimal("0")

    for row in rows:
        if row.match_kind is BookingReconcileMatchKind.MATCHED:
            matched += 1
        elif row.match_kind is BookingReconcileMatchKind.MISSING_IN_STAY:
            missing_in_stay += 1
        elif row.match_kind is BookingReconcileMatchKind.MISSING_IN_BOOKING:
            missing_in_booking += 1
        elif row.match_kind is BookingReconcileMatchKind.PARSE_ERROR:
            parse_errors += 1

        if row.has_differences:
            rows_with_differences += 1
        if row.is_fixable:
            fixable_rows += 1

        if row.match_kind in {
            BookingReconcileMatchKind.MATCHED,
            BookingReconcileMatchKind.MISSING_IN_STAY,
        }:
            if row.booking_amount is not None:
                booking_total_amount += row.booking_amount
            if row.booking_commission is not None:
                booking_total_commission += row.booking_commission

        if row.match_kind in {
            BookingReconcileMatchKind.MATCHED,
            BookingReconcileMatchKind.MISSING_IN_BOOKING,
        }:
            if row.stay_amount is not None:
                stay_total_amount += row.stay_amount
            if row.stay_commission is not None:
                stay_total_commission += row.stay_commission

    return BookingReconcileSummary(
        total_rows=len(rows),
        matched=matched,
        missing_in_stay=missing_in_stay,
        missing_in_booking=missing_in_booking,
        parse_errors=parse_errors,
        rows_with_differences=rows_with_differences,
        fixable_rows=fixable_rows,
        booking_total_amount=booking_total_amount,
        stay_total_amount=stay_total_amount,
        booking_total_commission=booking_total_commission,
        stay_total_commission=stay_total_commission,
    )
