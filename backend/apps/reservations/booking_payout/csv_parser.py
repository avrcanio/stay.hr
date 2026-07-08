from __future__ import annotations

import csv
import hashlib
import html
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from apps.reservations.booking_payout.types import BookingPayoutRowDTO

REQUIRED_HEADERS = {
    "Type",
    "Booking number",
    "Check-in",
    "Checkout",
    "Guest name",
    "Reservation status",
    "Currency",
    "Amount",
    "Commission",
    "Payments Service Fee",
    "Net",
    "Payout date",
    "Payout ID",
}

DATE_FORMAT = "%b %d, %Y"


class BookingPayoutCsvParseError(Exception):
    def __init__(self, message: str, *, line_number: int | None = None):
        super().__init__(message)
        self.line_number = line_number


def sha256_file_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_booking_date(value: str) -> date:
    text = html.unescape((value or "").strip())
    if not text:
        raise BookingPayoutCsvParseError("Empty date value")
    try:
        return datetime.strptime(text, DATE_FORMAT).date()
    except ValueError as exc:
        raise BookingPayoutCsvParseError(f"Invalid date {text!r} (expected e.g. Jun 11, 2026)") from exc


def parse_decimal(value: str, *, field_name: str) -> Decimal:
    text = html.unescape((value or "").strip()).replace(",", "")
    if not text:
        raise BookingPayoutCsvParseError(f"Empty {field_name}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise BookingPayoutCsvParseError(f"Invalid decimal for {field_name}: {value!r}") from exc


class BookingPayoutCsvParser:
    """Parse Booking.com payout CSV into DTOs (no Django model imports)."""

    def parse_bytes(self, content: bytes) -> tuple[list[BookingPayoutRowDTO], str]:
        sha = sha256_file_content(content)
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise BookingPayoutCsvParseError("CSV has no header row")

        headers = {html.unescape(h.strip()) for h in reader.fieldnames if h}
        missing = REQUIRED_HEADERS - headers
        if missing:
            raise BookingPayoutCsvParseError(
                f"Missing required CSV columns: {', '.join(sorted(missing))}"
            )

        rows: list[BookingPayoutRowDTO] = []
        for line_number, raw in enumerate(reader, start=2):
            if not raw or not any((v or "").strip() for v in raw.values()):
                continue
            source_row = {
                html.unescape(k): html.unescape(v or "")
                for k, v in raw.items()
                if k is not None
            }
            row_type = source_row.get("Type", "").strip()
            if row_type and row_type.lower() != "reservation":
                continue
            rows.append(self._parse_row(line_number=line_number, source_row=source_row))

        if not rows:
            raise BookingPayoutCsvParseError("CSV contains no reservation rows")

        return rows, sha

    def _parse_row(self, *, line_number: int, source_row: dict[str, str]) -> BookingPayoutRowDTO:
        try:
            booking_number = source_row.get("Booking number", "").strip()
            if not booking_number:
                raise BookingPayoutCsvParseError("Missing booking number", line_number=line_number)

            gross = parse_decimal(source_row.get("Amount", ""), field_name="Amount")
            commission_raw = parse_decimal(source_row.get("Commission", ""), field_name="Commission")
            service_fee_raw = parse_decimal(
                source_row.get("Payments Service Fee", ""),
                field_name="Payments Service Fee",
            )
            net = parse_decimal(source_row.get("Net", ""), field_name="Net")
            currency = source_row.get("Currency", "").strip().upper()
            if len(currency) != 3:
                raise BookingPayoutCsvParseError(
                    f"Invalid currency {currency!r}", line_number=line_number
                )

            payout_id = source_row.get("Payout ID", "").strip()
            if not payout_id:
                raise BookingPayoutCsvParseError("Missing payout ID", line_number=line_number)

            return BookingPayoutRowDTO(
                line_number=line_number,
                source_row=source_row,
                booking_number=booking_number,
                guest_name=source_row.get("Guest name", "").strip(),
                check_in=parse_booking_date(source_row.get("Check-in", "")),
                check_out=parse_booking_date(source_row.get("Checkout", "")),
                gross_amount=gross,
                commission_amount=abs(commission_raw),
                service_fee=abs(service_fee_raw),
                net_amount=net,
                currency=currency,
                reservation_status=source_row.get("Reservation status", "").strip(),
                payout_date=parse_booking_date(source_row.get("Payout date", "")),
                payout_id=payout_id,
            )
        except BookingPayoutCsvParseError:
            raise
        except Exception as exc:
            raise BookingPayoutCsvParseError(str(exc), line_number=line_number) from exc
