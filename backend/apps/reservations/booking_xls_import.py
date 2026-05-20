from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import xlrd
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.reservations.reservation_units import (
    apply_unit_amounts_from_total,
    sync_reservation_units,
)
from apps.tenants.models import Tenant

IMPORT_SOURCE_BOOKING_XLS = "booking_xls"

LEGACY_XLS_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
BLOCKED_BOOKING_EXPORT_EXTENSIONS = (".xlsx", ".xlsm", ".csv", ".txt", ".pdf", ".zip", ".doc", ".docx")

XLS_HEADER_ALIASES = {
    "broj rezervacije": "external_id",
    "nositelj rezervacije": "booker_name",
    "ime(na) gosta": "guest_names",
    "prijava": "check_in_date",
    "odjava": "check_out_date",
    "rezervirano": "booked_at",
    "status": "booking_status",
    "jedinice": "units_count",
    "osobe": "persons_count",
    "odrasli": "adults_count",
    "djeca": "children_count",
    "dob djece": "children_ages",
    "cijena": "price",
    "provizija %": "commission_percent",
    "iznos provizije": "commission_amount",
    "status placanja": "payment_status",
    "status plaćanja": "payment_status",
    "nacin placanja (pruzatelj usluga naplate)": "payment_provider",
    "način plaćanja (pružatelj usluga naplate)": "payment_provider",
    "napomene": "notes",
    "booker country": "booker_country",
    "svrha putovanja": "travel_purpose",
    "uredaj": "booking_device",
    "uređaj": "booking_device",
    "vrsta jedinice": "room_name",
    "trajanje (nocenja)": "nights_count",
    "trajanje (noćenja)": "nights_count",
    "datum otkazivanja": "canceled_at",
    "adresa": "booker_address",
    "broj telefona": "booker_phone",
    "book number": "external_id",
    "booking number": "external_id",
    "booked by": "booker_name",
    "guest name(s)": "guest_names",
    "guest names": "guest_names",
    "check-in": "check_in_date",
    "check-in date": "check_in_date",
    "check-out": "check_out_date",
    "check-out date": "check_out_date",
    "booked on": "booked_at",
    "rooms": "units_count",
    "persons": "persons_count",
    "adults": "adults_count",
    "children": "children_count",
    "children's age(s)": "children_ages",
    "childrens age(s)": "children_ages",
    "price": "price",
    "commission %": "commission_percent",
    "commission amount": "commission_amount",
    "payment status": "payment_status",
    "payment method (payment provider)": "payment_provider",
    "remarks": "notes",
    "travel purpose": "travel_purpose",
    "device": "booking_device",
    "unit type": "room_name",
    "duration (nights)": "nights_count",
    "cancellation date": "canceled_at",
    "address": "booker_address",
    "phone number": "booker_phone",
}


@dataclass(frozen=True)
class BookingXlsRow:
    external_id: str
    booker_name: str
    guest_names: list[str]
    check_in_date: date
    check_out_date: date
    booked_at: datetime | None
    booking_status: str
    units_count: int | None
    persons_count: int | None
    adults_count: int | None
    children_count: int | None
    children_ages: str
    total_amount: Decimal | None
    currency: str
    commission_percent: Decimal | None
    commission_amount: Decimal | None
    payment_status: str
    payment_provider: str
    notes: str
    booker_country: str
    travel_purpose: str
    booking_device: str
    room_name: str
    nights_count: int | None
    canceled_at: datetime | None
    booker_address: str
    booker_phone: str


@dataclass(frozen=True)
class XlsImportResult:
    external_id: str
    created: bool
    skipped: bool = False
    updated: bool = False
    reservation_id: int | None = None


def is_legacy_xls_content(content: bytes) -> bool:
    return len(content) >= 8 and content[:8] == LEGACY_XLS_OLE_SIGNATURE


def validate_booking_export_file(*, filename: str, content: bytes) -> None:
    lower = (filename or "").lower()
    if any(lower.endswith(ext) for ext in BLOCKED_BOOKING_EXPORT_EXTENSIONS):
        raise ValueError(f"Datoteka '{filename}' nije podržana (koristite Booking .xls export).")
    if not is_legacy_xls_content(content):
        raise ValueError(
            f"Datoteka '{filename}' nije stari Excel (.xls) format. "
            "Booking export mora biti .xls (Excel 97–2003), ne .xlsx."
        )


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_money(value: Any) -> tuple[Decimal | None, str]:
    raw = _cell_str(value)
    if not raw:
        return (None, "EUR")
    match = re.match(r"^([\d.,]+)\s*([A-Za-z]{3})?$", raw.replace(" ", ""))
    if not match:
        try:
            return (Decimal(raw.replace(",", ".")), "EUR")
        except InvalidOperation:
            return (None, "EUR")
    amount_raw, currency = match.group(1), (match.group(2) or "EUR")
    try:
        return (Decimal(amount_raw.replace(",", ".")), currency.upper())
    except InvalidOperation:
        return (None, currency.upper())


def _parse_decimal(value: Any) -> Decimal | None:
    raw = _cell_str(value)
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None


def _parse_int(value: Any) -> int | None:
    raw = _cell_str(value)
    if not raw:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _parse_xls_datetime(value: Any, book: xlrd.book.Book) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            dt_tuple = xlrd.xldate_as_tuple(value, book.datemode)
            dt = datetime(*dt_tuple[:6])
        except Exception:
            return None
    else:
        raw = _cell_str(value)
        if not raw:
            return None
        parsed = parse_datetime(raw)
        if parsed:
            dt = parsed
        else:
            d = parse_date(raw)
            if not d:
                return None
            dt = datetime.combine(d, datetime.min.time())
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_xls_date(value: Any, book: xlrd.book.Book) -> date | None:
    dt = _parse_xls_datetime(value, book)
    if dt:
        return dt.date()
    raw = _cell_str(value)
    if not raw:
        return None
    return parse_date(raw[:10]) if len(raw) >= 10 else parse_date(raw)


def _split_guest_names(raw: str) -> list[str]:
    if not raw:
        return []
    text = raw.strip()
    if ";" in text:
        return [p.strip() for p in text.split(";") if p.strip()]
    if "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) > 1 and all(len(part.split()) >= 2 for part in parts):
            return parts
    return [text]


def _parse_guest_name(full_name: str) -> tuple[str, str]:
    name = html.unescape((full_name or "").strip())
    if not name:
        return ("", "")
    if "," in name:
        last, _, first = name.partition(",")
        return (first.strip() or "-", last.strip() or "-")
    parts = [p for p in name.split() if p]
    if len(parts) == 1:
        return (parts[0], "")
    return (" ".join(parts[:-1]), parts[-1])


def _operational_status_from_booking(booking_status: str) -> str:
    normalized = (booking_status or "").strip().lower()
    if normalized in {"cancelled_by_guest", "cancelled", "canceled", "cancelled_by_hotel"}:
        return Reservation.Status.CANCELED
    return Reservation.Status.EXPECTED


def _map_row_dict(raw: dict[str, Any], book: xlrd.book.Book) -> BookingXlsRow:
    external_id = _cell_str(raw.get("external_id"))
    if not external_id:
        raise ValueError("Missing booking number")
    try:
        external_id = str(int(float(external_id)))
    except (TypeError, ValueError):
        pass

    check_in = _parse_xls_date(raw.get("check_in_date"), book)
    check_out = _parse_xls_date(raw.get("check_out_date"), book)
    if not check_in or not check_out:
        raise ValueError(f"Missing check-in/out dates for booking {external_id}")

    total_amount, currency = _parse_money(raw.get("price"))

    return BookingXlsRow(
        external_id=external_id,
        booker_name=_cell_str(raw.get("booker_name")),
        guest_names=_split_guest_names(_cell_str(raw.get("guest_names"))),
        check_in_date=check_in,
        check_out_date=check_out,
        booked_at=_parse_xls_datetime(raw.get("booked_at"), book),
        booking_status=_cell_str(raw.get("booking_status")),
        units_count=_parse_int(raw.get("units_count")),
        persons_count=_parse_int(raw.get("persons_count")),
        adults_count=_parse_int(raw.get("adults_count")),
        children_count=_parse_int(raw.get("children_count")),
        children_ages=_cell_str(raw.get("children_ages")),
        total_amount=total_amount,
        currency=currency,
        commission_percent=_parse_decimal(raw.get("commission_percent")),
        commission_amount=_parse_money(raw.get("commission_amount"))[0],
        payment_status=_cell_str(raw.get("payment_status")),
        payment_provider=_cell_str(raw.get("payment_provider")),
        notes=html.unescape(_cell_str(raw.get("notes"))),
        booker_country=_cell_str(raw.get("booker_country")).upper()[:8],
        travel_purpose=_cell_str(raw.get("travel_purpose")),
        booking_device=_cell_str(raw.get("booking_device")),
        room_name=_cell_str(raw.get("room_name")) or "Unknown",
        nights_count=_parse_int(raw.get("nights_count")),
        canceled_at=_parse_xls_datetime(raw.get("canceled_at"), book),
        booker_address=_cell_str(raw.get("booker_address")),
        booker_phone=_cell_str(raw.get("booker_phone")),
    )


def parse_booking_xls_workbook(book) -> list[BookingXlsRow]:
    sheet = book.sheet_by_index(0)
    if sheet.nrows < 2:
        return []

    header_map: dict[int, str] = {}
    for col in range(sheet.ncols):
        label = _normalize_header(_cell_str(sheet.cell_value(0, col)))
        field = XLS_HEADER_ALIASES.get(label)
        if field:
            header_map[col] = field

    rows: list[BookingXlsRow] = []
    for row_idx in range(1, sheet.nrows):
        raw: dict[str, Any] = {}
        empty = True
        for col, field in header_map.items():
            value = sheet.cell_value(row_idx, col)
            if _cell_str(value):
                empty = False
            raw[field] = value
        if empty:
            continue
        rows.append(_map_row_dict(raw, book))
    return rows


def parse_booking_xls(path: str) -> list[BookingXlsRow]:
    return parse_booking_xls_workbook(xlrd.open_workbook(path))


def parse_booking_xls_bytes(content: bytes) -> list[BookingXlsRow]:
    return parse_booking_xls_workbook(xlrd.open_workbook(file_contents=content))


def _sync_guests(
    *,
    tenant: Tenant,
    reservation: Reservation,
    guest_names: list[str],
    booker_country: str,
    booker_email: str,
) -> None:
    if not guest_names:
        return

    Guest.objects.filter(reservation=reservation).update(is_primary=False)
    for idx, full_name in enumerate(guest_names):
        first_name, last_name = _parse_guest_name(full_name)
        if not first_name and not last_name:
            continue
        is_primary = idx == 0
        guest = Guest.objects.filter(
            reservation=reservation,
            first_name=first_name or "-",
            last_name=last_name or "-",
        ).first()
        if guest is None:
            Guest.objects.create(
                tenant=tenant,
                reservation=reservation,
                first_name=first_name or "-",
                last_name=last_name or "-",
                name=f"{first_name} {last_name}".strip(),
                email=booker_email if is_primary else "",
                nationality=booker_country if is_primary else "",
                document_country_iso2=booker_country if is_primary else "",
                is_primary=is_primary,
            )
        else:
            guest.is_primary = is_primary
            guest.name = f"{first_name} {last_name}".strip()
            if is_primary and booker_email:
                guest.email = booker_email
            if is_primary and booker_country and not guest.nationality:
                guest.nationality = booker_country
                guest.document_country_iso2 = booker_country
            guest.save(
                update_fields=[
                    "is_primary",
                    "name",
                    "email",
                    "nationality",
                    "document_country_iso2",
                    "updated_at",
                ]
            )


@transaction.atomic
def upsert_reservation_from_xls_row(
    *,
    tenant: Tenant,
    property: Property,
    row: BookingXlsRow,
    skip_existing: bool = True,
) -> XlsImportResult:
    existing = Reservation.objects.filter(
        tenant=tenant,
        external_id=row.external_id,
    ).first()

    if existing is not None and skip_existing:
        return XlsImportResult(
            external_id=row.external_id,
            created=False,
            skipped=True,
            updated=False,
            reservation_id=existing.id,
        )

    new_status = _operational_status_from_booking(row.booking_status)
    now = timezone.now()
    booker_email = ""
    if row.booker_name and "@" not in row.booker_name:
        slug = re.sub(r"[^a-z0-9]+", ".", row.booker_name.lower()).strip(".")
        if slug:
            booker_email = f"{slug}@booking-import.local"

    defaults = {
        "property": property,
        "booking_code": row.external_id,
        "check_in": row.check_in_date,
        "check_out": row.check_out_date,
        "status": new_status,
        "booker_name": row.booker_name or "Booking guest",
        "booker_email": booker_email,
        "booker_phone": row.booker_phone,
        "booker_country": row.booker_country,
        "booker_address": row.booker_address,
        "amount": row.total_amount,
        "currency": row.currency or "EUR",
        "source": "Booking.com",
        "import_source": IMPORT_SOURCE_BOOKING_XLS,
        "imported_at": now,
        "booked_at": row.booked_at,
        "booking_status": row.booking_status,
        "units_count": row.units_count,
        "persons_count": row.persons_count,
        "adults_count": row.adults_count,
        "children_count": row.children_count,
        "children_ages": row.children_ages,
        "commission_percent": row.commission_percent,
        "commission_amount": row.commission_amount,
        "payment_status": row.payment_status,
        "payment_provider": row.payment_provider,
        "notes": row.notes,
        "travel_purpose": row.travel_purpose,
        "booking_device": row.booking_device,
        "nights_count": row.nights_count,
        "canceled_at": row.canceled_at,
        "details_pending": False,
    }

    if existing is None:
        reservation = Reservation.objects.create(
            tenant=tenant,
            external_id=row.external_id,
            **defaults,
        )
        created = True
    else:
        reservation = existing
        created = False
        if reservation.status in (
            Reservation.Status.CHECKED_IN,
            Reservation.Status.CHECKED_OUT,
        ):
            defaults["status"] = reservation.status
        for field, value in defaults.items():
            setattr(reservation, field, value)
        reservation.save()

    _sync_guests(
        tenant=tenant,
        reservation=reservation,
        guest_names=row.guest_names or ([row.booker_name] if row.booker_name else []),
        booker_country=row.booker_country,
        booker_email=booker_email,
    )
    units = sync_reservation_units(
        tenant=tenant,
        property=property,
        reservation=reservation,
        room_name=row.room_name,
    )
    apply_unit_amounts_from_total(
        reservation=reservation,
        total_amount=row.total_amount,
        units=units,
    )

    return XlsImportResult(
        external_id=row.external_id,
        created=created,
        skipped=False,
        updated=not created,
        reservation_id=reservation.id,
    )


def import_booking_xls_rows(
    *,
    tenant: Tenant,
    property: Property,
    rows: list[BookingXlsRow],
    dry_run: bool = False,
    skip_existing: bool = True,
) -> dict[str, Any]:
    stats: dict[str, Any] = {"created": 0, "updated": 0, "skipped": 0, "errors": [], "rows": []}

    for row in rows:
        try:
            if dry_run:
                exists = Reservation.objects.filter(
                    tenant=tenant,
                    external_id=row.external_id,
                ).exists()
                if exists and skip_existing:
                    action = "skipped"
                    stats["skipped"] += 1
                elif exists:
                    action = "updated"
                    stats["updated"] += 1
                else:
                    action = "created"
                    stats["created"] += 1
                stats["rows"].append(
                    {
                        "external_id": row.external_id,
                        "action": action,
                        "check_in": row.check_in_date.isoformat(),
                        "room_name": row.room_name,
                    }
                )
                continue

            result = upsert_reservation_from_xls_row(
                tenant=tenant,
                property=property,
                row=row,
                skip_existing=skip_existing,
            )
            if result.skipped:
                stats["skipped"] += 1
            elif result.created:
                stats["created"] += 1
            else:
                stats["updated"] += 1
            stats["rows"].append(
                {
                    "external_id": row.external_id,
                    "reservation_id": result.reservation_id,
                    "created": result.created,
                    "skipped": result.skipped,
                }
            )
        except Exception as exc:
            stats["errors"].append({"external_id": row.external_id, "error": str(exc)})

    stats["total"] = len(rows)
    return stats


def import_booking_xls_file(
    path: str,
    *,
    tenant: Tenant,
    property: Property,
    dry_run: bool = False,
    check_in_from: date | None = None,
    check_in_to: date | None = None,
    skip_existing: bool = True,
) -> dict[str, Any]:
    rows = parse_booking_xls(path)
    if check_in_from or check_in_to:
        filtered: list[BookingXlsRow] = []
        for row in rows:
            if check_in_from and row.check_in_date < check_in_from:
                continue
            if check_in_to and row.check_in_date > check_in_to:
                continue
            filtered.append(row)
        rows = filtered
    return import_booking_xls_rows(
        tenant=tenant,
        property=property,
        rows=rows,
        dry_run=dry_run,
        skip_existing=skip_existing,
    )
