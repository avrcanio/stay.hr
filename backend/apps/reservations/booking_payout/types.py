from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from django.db import models

from apps.reservations.booking_payout_models import BookingPayoutWarningSeverity


class SyncPolicy(models.TextChoices):
    SAFE = "safe", "Safe (payout fields only)"
    MANUAL_OVERRIDE = "manual_override", "Manual override (amounts + payout)"
    FORCE = "force", "Force (superuser only)"


class BookingPayoutSyncErrorCode(models.TextChoices):
    INVOICE_EXISTS = "invoice_exists", "Invoice exists"
    RESERVATION_MISSING = "reservation_missing", "Reservation missing"
    PAYOUT_ID_CONFLICT = "payout_id_conflict", "Payout ID conflict"
    STALE_REVISION = "stale_revision", "Stale revision"
    INVALID_STATUS = "invalid_status", "Invalid status"
    INVALID_TRANSITION = "invalid_transition", "Invalid transition"
    PERMISSION_DENIED = "permission_denied", "Permission denied"
    UNMATCHED = "unmatched", "Line unmatched"
    DUPLICATE = "duplicate", "Duplicate line"
    INVALID_POLICY = "invalid_policy", "Invalid policy"


class BookingPayoutSyncError(Exception):
    def __init__(
        self,
        code: BookingPayoutSyncErrorCode | str,
        message: str = "",
    ) -> None:
        self.code = code
        self.message = message or str(code)
        super().__init__(self.message)


@dataclass(frozen=True)
class FieldDiff:
    field: str
    old: str | None
    new: str | None
    changed: bool


@dataclass
class SyncLineResult:
    line_id: int
    result: Literal["SUCCESS", "NO_CHANGES", "FAILED"]
    error_code: BookingPayoutSyncErrorCode | None
    field_diffs: list[FieldDiff]
    updated_fields_count: int
    duration_ms: int


@dataclass
class SyncBatchResult:
    line_results: list[SyncLineResult]
    success: int
    no_changes: int
    failed: int
    duration_ms: int


@dataclass(frozen=True)
class BookingPayoutRowDTO:
    line_number: int
    source_row: dict[str, str]
    booking_number: str
    guest_name: str
    check_in: date
    check_out: date
    gross_amount: Decimal
    commission_amount: Decimal
    service_fee: Decimal
    net_amount: Decimal
    currency: str
    reservation_status: str
    payout_date: date
    payout_id: str


@dataclass
class PayoutPreviewLine:
    dto: BookingPayoutRowDTO
    match_status: str
    reservation_id: int | None
    warnings: dict[str, dict]


@dataclass
class PayoutPreviewResult:
    payout_id: str
    payout_date: date
    currency: str
    source_sha256: str
    lines: list[PayoutPreviewLine]
    batch_errors: list[str] = field(default_factory=list)


@dataclass
class LineApplyResult:
    line_number: int
    booking_number: str
    action: str
    message: str = ""


@dataclass
class PayoutImportResult:
    parsed: int
    matched: int
    unmatched: int
    duplicates: int
    applied: int
    skipped: int
    warnings: int
    errors: int
    duration_ms: int
    line_results: list[LineApplyResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "parsed": self.parsed,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "duplicates": self.duplicates,
            "applied": self.applied,
            "skipped": self.skipped,
            "warnings": self.warnings,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }


_SEVERITY_ORDER = {
    BookingPayoutWarningSeverity.INFO: 0,
    BookingPayoutWarningSeverity.WARNING: 1,
    BookingPayoutWarningSeverity.ERROR: 2,
}


def highest_warning_severity(warnings: dict | None) -> str | None:
    if not warnings:
        return None
    best: str | None = None
    best_rank = -1
    for entry in warnings.values():
        if not isinstance(entry, dict):
            continue
        severity = entry.get("severity")
        if severity not in _SEVERITY_ORDER:
            continue
        rank = _SEVERITY_ORDER[severity]
        if rank > best_rank:
            best_rank = rank
            best = severity
    return best


def warning_entry(
    severity: str,
    *,
    message: str = "",
    reservation: str | Decimal | None = None,
    csv: str | Decimal | None = None,
) -> dict:
    entry: dict[str, str] = {"severity": severity}
    if message:
        entry["message"] = message
    if reservation is not None:
        entry["reservation"] = str(reservation)
    if csv is not None:
        entry["csv"] = str(csv)
    return entry
