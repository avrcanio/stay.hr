"""Seed historical mock reservations (2025–2026) on demo tenant for calendar/statistics UI."""

from __future__ import annotations

import secrets
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.management.commands.seed_demo_reservations import (
    GUEST_PROFILES,
    MOCK_BOOKING_PREFIX,
)
from apps.tenants.models import Tenant

HIST_PREFIX = f"{MOCK_BOOKING_PREFIX}HIST-"
SOURCES = ("Booking.com", "Direct", "Airbnb", "Expedia", "Hotels.com")
UNIT_CODES = ("STD-01", "STD-02", "APT-01")


class Command(BaseCommand):
    help = (
        "Seed MOCK-HIST-* reservations across 2025–2026 on demo tenant. "
        "Past stays (check_out <= today) are checked_out; includes canceled rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=1)
        parser.add_argument("--from-year", type=int, default=2025)
        parser.add_argument("--to-year", type=int, default=2026)
        parser.add_argument(
            "--per-month",
            type=int,
            default=5,
            help="Reservations per month (last one is canceled).",
        )
        parser.add_argument(
            "--property-slug",
            default="demo",
            help="Property slug on tenant (default: demo).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if not tenant:
            raise CommandError(f"Tenant id={options['tenant_id']} not found.")

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        if not prop:
            raise CommandError(f"Property slug={options['property_slug']!r} not found.")

        units = {
            u.code: u
            for u in Unit.objects.filter(tenant=tenant, property=prop, code__in=UNIT_CODES)
        }
        missing = [c for c in UNIT_CODES if c not in units]
        if missing:
            raise CommandError(f"Missing unit codes on {prop.slug}: {missing}")

        today = timezone.localdate()
        per_month = max(options["per_month"], 2)
        created = updated = 0

        for year in range(options["from_year"], options["to_year"] + 1):
            for month in range(1, 13):
                days_in_month = monthrange(year, month)[1]
                for seq in range(1, per_month + 1):
                    is_canceled = seq == per_month
                    day = min(1 + (seq - 1) * (days_in_month // per_month), days_in_month)
                    nights = 2 + ((year + month + seq) % 4)
                    check_in = date(year, month, day)
                    check_out = check_in + timedelta(days=nights)
                    if check_out <= check_in:
                        check_out = check_in + timedelta(days=1)

                    status = self._resolve_status(
                        is_canceled=is_canceled,
                        check_in=check_in,
                        check_out=check_out,
                        today=today,
                    )
                    nightly = self._nightly_rate(year, month)
                    amount = Decimal("0.00") if is_canceled else (nightly * nights).quantize(
                        Decimal("0.01")
                    )
                    commission = (
                        None
                        if is_canceled or amount <= 0
                        else (amount * Decimal("0.12")).quantize(Decimal("0.01"))
                    )

                    spec = {
                        "booking_code": f"{HIST_PREFIX}{year}-{month:02d}-{seq:02d}",
                        "property": prop,
                        "unit": units[UNIT_CODES[(month + seq) % len(UNIT_CODES)]],
                        "status": status,
                        "check_in": check_in,
                        "check_out": check_out,
                        "amount": amount,
                        "commission_amount": commission,
                        "source": SOURCES[(month + seq) % len(SOURCES)],
                        "profile_idx": (year * 12 + month + seq) % len(GUEST_PROFILES),
                        "is_canceled": is_canceled,
                    }
                    _, was_created = self._upsert_reservation(tenant, spec)
                    if was_created:
                        created += 1
                    else:
                        updated += 1

        total_hist = Reservation.objects.filter(
            tenant=tenant, booking_code__startswith=HIST_PREFIX
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"History seed done: {created} created, {updated} updated. "
                f"MOCK-HIST-* total: {total_hist}"
            )
        )

    @staticmethod
    def _resolve_status(
        *,
        is_canceled: bool,
        check_in: date,
        check_out: date,
        today: date,
    ) -> str:
        if is_canceled:
            return Reservation.Status.CANCELED
        if check_in <= today:
            return Reservation.Status.CHECKED_OUT
        return Reservation.Status.EXPECTED

    @staticmethod
    def _nightly_rate(year: int, month: int) -> Decimal:
        base = Decimal("85.00")
        if month in (6, 7, 8):
            base = Decimal("125.00")
        elif month in (4, 5, 9, 10):
            base = Decimal("105.00")
        elif month in (12, 1, 2):
            base = Decimal("75.00")
        if year >= 2026:
            base *= Decimal("1.05")
        return base

    def _upsert_reservation(self, tenant: Tenant, spec: dict) -> tuple[Reservation, bool]:
        nights = max((spec["check_out"] - spec["check_in"]).days, 0)
        profile = GUEST_PROFILES[spec["profile_idx"] % len(GUEST_PROFILES)]
        first, last, nat, booker_country, domain = profile
        full_name = f"{first} {last}".strip()
        email = f"{first.lower()}.{last.lower().replace(' ', '')}@{domain}"

        defaults = {
            "property": spec["property"],
            "check_in": spec["check_in"],
            "check_out": spec["check_out"],
            "status": spec["status"],
            "booker_name": full_name,
            "booker_email": email,
            "booker_phone": f"+38598{secrets.randbelow(9000000) + 1000000:07d}"[-11:],
            "booker_country": booker_country,
            "booker_address": self._mock_address(booker_country),
            "amount": spec["amount"],
            "commission_amount": spec.get("commission_amount"),
            "commission_percent": Decimal("12.00") if spec.get("commission_amount") else None,
            "currency": "EUR",
            "source": spec["source"],
            "import_source": "demo_history",
            "units_count": 1,
            "persons_count": 2,
            "adults_count": 2,
            "nights_count": nights,
            "payment_status": "" if spec["is_canceled"] else "paid",
            "booked_at": timezone.make_aware(
                datetime.combine(spec["check_in"], datetime.min.time())
            ),
            "canceled_at": timezone.now() if spec["is_canceled"] else None,
        }

        reservation, created = Reservation.objects.update_or_create(
            tenant=tenant,
            booking_code=spec["booking_code"],
            defaults=defaults,
        )

        unit: Unit = spec["unit"]
        ReservationUnit.objects.update_or_create(
            tenant=tenant,
            reservation=reservation,
            sort_order=0,
            defaults={"unit": unit, "room_name": unit.name, "amount": spec["amount"]},
        )

        Guest.objects.filter(reservation=reservation).delete()
        Guest.objects.create(
            tenant=tenant,
            reservation=reservation,
            first_name=first,
            last_name=last,
            name=full_name,
            email=email,
            nationality=nat,
            document_country_iso2=nat,
            document_country=nat,
            is_primary=True,
        )
        return reservation, created

    @staticmethod
    def _mock_address(country: str) -> str:
        from apps.tenants.management.commands import seed_demo_reservations as sdr

        return sdr.Command._mock_address(country)
