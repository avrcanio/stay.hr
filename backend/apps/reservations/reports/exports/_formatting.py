"""Display formatting for property financial report exports."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from apps.reservations.reports.types import PropertyFinancialReportResult
from apps.reservations.statistics import _decimal_str

EXCEL_SHEET_TITLE = "Financial report"
EXCEL_MONEY_NUMBER_FORMAT = "#,##0.00"
EXCEL_DATE_NUMBER_FORMAT = "dd.mm.yyyy"
EXCEL_DATETIME_NUMBER_FORMAT = "dd.mm.yyyy hh:mm"


def format_decimal(value: Decimal | None, *, null_as_zero: bool = False) -> str:
    if value is None:
        if null_as_zero:
            return _decimal_str(Decimal("0"))
        return ""
    return _decimal_str(value)


def format_decimal_hr(value: Decimal | None, *, null_as_zero: bool = False) -> str:
    text = format_decimal(value, null_as_zero=null_as_zero)
    if not text:
        return "—"
    return text.replace(".", ",")


def format_date_hr(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_datetime_hr(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def format_period_iso(check_out_from: date, check_out_to: date) -> str:
    return f"{check_out_from.isoformat()} – {check_out_to.isoformat()}"


def format_guest_names(result_row_guests) -> str:
    if not result_row_guests:
        return ""
    return "; ".join(guest.name for guest in result_row_guests)


def export_filename(result: PropertyFinancialReportResult, extension: str) -> str:
    meta = result.meta
    slug = meta.property_slug or "property"
    from_date = meta.check_out_from.isoformat()
    to_date = meta.check_out_to.isoformat()
    return f"property-financial-{slug}-{from_date}_{to_date}.{extension}"


def apply_excel_money_format(cell) -> None:
    if cell.value is not None:
        cell.number_format = EXCEL_MONEY_NUMBER_FORMAT


def write_excel_money_cell(cell, value: Decimal | None, *, null_as_zero: bool = False) -> None:
    if value is None:
        if null_as_zero:
            cell.value = Decimal("0")
            apply_excel_money_format(cell)
        else:
            cell.value = None
        return
    cell.value = value
    apply_excel_money_format(cell)
