"""Dataclass types for the property financial report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from django.conf import settings
from django.utils.dateparse import parse_date

from apps.properties.models import Property
from apps.properties.resolution import PropertyResolutionError, resolve_property_for_tenant
from apps.tenants.models import Tenant


class PropertyFinancialReportParamsError(Exception):
    """Invalid report parameters."""

    def __init__(self, code: str, *, detail: str = "", max_days: int | None = None):
        self.code = code
        self.detail = detail
        self.max_days = max_days
        super().__init__(code)


@dataclass(frozen=True)
class PropertyFinancialReportParams:
    tenant: Tenant
    property: Property
    check_out_from: date
    check_out_to_exclusive: date

    @classmethod
    def from_query(
        cls,
        tenant: Tenant,
        *,
        property_slug: str | None,
        check_out_from: str | None,
        check_out_to: str | None,
    ) -> PropertyFinancialReportParams:
        parsed_from = parse_date((check_out_from or "").strip())
        parsed_to = parse_date((check_out_to or "").strip())
        if parsed_from is None or parsed_to is None:
            raise PropertyFinancialReportParamsError("period_invalid")

        try:
            prop = resolve_property_for_tenant(tenant, slug=property_slug)
        except PropertyResolutionError as exc:
            message = exc.message if hasattr(exc, "message") else str(exc)
            if isinstance(message, dict):
                detail = next(iter(message.values()), str(message))
                if isinstance(detail, list):
                    detail = detail[0] if detail else str(message)
            else:
                detail = str(message)
            raise PropertyFinancialReportParamsError(
                "property_required",
                detail=str(detail),
            ) from exc

        params = cls(
            tenant=tenant,
            property=prop,
            check_out_from=parsed_from,
            check_out_to_exclusive=parsed_to + timedelta(days=1),
        )
        params.validate()
        return params

    def validate(self) -> None:
        if self.check_out_to_exclusive <= self.check_out_from:
            raise PropertyFinancialReportParamsError("period_invalid")

        max_days = settings.PROPERTY_FINANCIAL_REPORT_MAX_DAYS
        span_days = (self.check_out_to_exclusive - self.check_out_from).days
        if span_days > max_days:
            raise PropertyFinancialReportParamsError(
                "period_too_long",
                max_days=max_days,
            )

    @property
    def check_out_to_inclusive(self) -> date:
        return self.check_out_to_exclusive - timedelta(days=1)


class PayoutStatus(StrEnum):
    PAID = "paid"
    NOT_PAID = "not_paid"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class PropertyFinancialReportGuestRow:
    name: str
    nationality_iso2: str
    is_primary: bool


@dataclass(frozen=True)
class PropertyFinancialReportRow:
    reservation_id: int
    booking_code: str
    external_id: str
    check_in: date
    check_out: date
    status: str
    room_labels: tuple[str, ...]
    nights: int
    gross: Decimal | None
    commission: Decimal | None
    net: Decimal | None
    currency: str
    source: str
    guests: tuple[PropertyFinancialReportGuestRow, ...]
    payout_status: PayoutStatus
    payout_received_at: date | None
    paid_amount: Decimal | None


@dataclass(frozen=True)
class PropertyFinancialReportTotals:
    reservation_count: int
    nights: int
    gross: Decimal
    commission: Decimal
    net: Decimal


@dataclass(frozen=True)
class PropertyFinancialReportMeta:
    property_name: str
    property_slug: str
    check_out_from: date
    check_out_to: date
    generated_at: datetime
    currency: str
    max_period_days: int
    rows_with_missing_commission: int
    rows_without_confirmed_payout: int


@dataclass(frozen=True)
class PropertyFinancialReportResult:
    meta: PropertyFinancialReportMeta
    rows: tuple[PropertyFinancialReportRow, ...]
    totals: PropertyFinancialReportTotals
