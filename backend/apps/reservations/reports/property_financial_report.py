"""Property financial report — checked-out reservations by check_out period."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone

from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.reservations.nationality_display import guest_nationality_iso2
from apps.reservations.reports.types import (
    PropertyFinancialReportGuestRow,
    PropertyFinancialReportMeta,
    PropertyFinancialReportParams,
    PropertyFinancialReportResult,
    PropertyFinancialReportRow,
    PropertyFinancialReportTotals,
)
from apps.reservations.statistics import DEFAULT_CURRENCY, _effective_nights


def _room_labels(reservation: Reservation) -> tuple[str, ...]:
    labels: list[str] = []
    for unit_row in reservation.units.all():
        label = (unit_row.room_name or "").strip()
        if not label and unit_row.unit_id and unit_row.unit is not None:
            label = (unit_row.unit.code or unit_row.unit.name or "").strip()
        if label:
            labels.append(label)
    return tuple(labels)


def _guest_rows(reservation: Reservation) -> tuple[PropertyFinancialReportGuestRow, ...]:
    rows: list[PropertyFinancialReportGuestRow] = []
    for guest in reservation.guests.all():
        rows.append(
            PropertyFinancialReportGuestRow(
                name=guest.name or f"{guest.first_name} {guest.last_name}".strip(),
                nationality_iso2=guest_nationality_iso2(guest),
                is_primary=guest.is_primary,
            )
        )
    return tuple(rows)


def _row_net(amount: Decimal | None, commission: Decimal | None) -> Decimal | None:
    if commission is None:
        return None
    gross = amount or Decimal("0")
    return gross - commission


def build_property_financial_report(
    params: PropertyFinancialReportParams,
) -> PropertyFinancialReportResult:
    queryset = (
        Reservation.objects.for_tenant(params.tenant)
        .filter(
            property=params.property,
            status=Reservation.Status.CHECKED_OUT,
            check_out__gte=params.check_out_from,
            check_out__lt=params.check_out_to_exclusive,
        )
        .select_related("property")
        .prefetch_related(
            Prefetch(
                "guests",
                queryset=Guest.objects.order_by("-is_primary", "id"),
            ),
            Prefetch(
                "units",
                queryset=ReservationUnit.objects.select_related("unit").order_by("sort_order"),
            ),
        )
        .order_by("check_out", "check_in", "id")
    )

    rows: list[PropertyFinancialReportRow] = []
    currency = DEFAULT_CURRENCY
    total_nights = 0
    total_gross = Decimal("0")
    total_commission = Decimal("0")
    total_net = Decimal("0")
    rows_with_missing_commission = 0

    for reservation in queryset:
        nights = _effective_nights(reservation)
        gross = reservation.amount
        commission = reservation.commission_amount
        net = _row_net(gross, commission)

        if reservation.currency:
            currency = reservation.currency

        total_nights += nights
        total_gross += gross or Decimal("0")
        total_commission += commission or Decimal("0")
        if net is None:
            rows_with_missing_commission += 1
        else:
            total_net += net

        rows.append(
            PropertyFinancialReportRow(
                reservation_id=reservation.id,
                booking_code=reservation.booking_code or "",
                external_id=reservation.external_id or "",
                check_in=reservation.check_in,
                check_out=reservation.check_out,
                status=reservation.status,
                room_labels=_room_labels(reservation),
                nights=nights,
                gross=gross,
                commission=commission,
                net=net,
                currency=reservation.currency or DEFAULT_CURRENCY,
                source=reservation.source or "",
                guests=_guest_rows(reservation),
            )
        )

    return PropertyFinancialReportResult(
        meta=PropertyFinancialReportMeta(
            property_name=params.property.name,
            property_slug=params.property.slug,
            check_out_from=params.check_out_from,
            check_out_to=params.check_out_to_inclusive,
            generated_at=timezone.now(),
            currency=currency,
            max_period_days=settings.PROPERTY_FINANCIAL_REPORT_MAX_DAYS,
            rows_with_missing_commission=rows_with_missing_commission,
        ),
        rows=tuple(rows),
        totals=PropertyFinancialReportTotals(
            reservation_count=len(rows),
            nights=total_nights,
            gross=total_gross,
            commission=total_commission,
            net=total_net,
        ),
    )
