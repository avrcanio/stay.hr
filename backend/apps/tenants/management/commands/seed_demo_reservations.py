from __future__ import annotations

import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant

MOCK_BOOKING_PREFIX = "MOCK-"

# (first_name, last_name, nationality_iso2, booker_country, email_domain)
GUEST_PROFILES = [
    ("Luka", "Horvat", "HR", "HR", "example.hr"),
    ("Anna", "Müller", "DE", "DE", "example.de"),
    ("Thomas", "Weber", "AT", "AT", "example.at"),
    ("Giulia", "Rossi", "IT", "IT", "example.it"),
    ("James", "Smith", "GB", "GB", "example.co.uk"),
    ("Emily", "Johnson", "US", "US", "example.com"),
    ("Sophie", "Martin", "FR", "FR", "example.fr"),
    ("Marko", "Novak", "SI", "SI", "example.si"),
    ("Elena", "García", "ES", "ES", "example.es"),
    ("Jan", "de Vries", "NL", "NL", "example.nl"),
    ("Marco", "Bianchi", "CH", "CH", "example.ch"),
    ("Petra", "Kovač", "HR", "HR", "example.hr"),
    ("Oliver", "Brown", "IE", "IE", "example.ie"),
    ("Nina", "Johansson", "SE", "SE", "example.se"),
    ("Ante", "Vrcan", "HR", "HR", "example.hr"),
]


class Command(BaseCommand):
    help = (
        "Seed mock reservations and guests on demo tenant for a richer Flutter/reception UI. "
        "Idempotent on booking codes MOCK-*; refreshes existing demo guests."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=1,
            help="Tenant primary key (default: 1 = demo).",
        )
        parser.add_argument(
            "--only-refresh-guests",
            action="store_true",
            help="Only update guests on existing reservations, skip creating MOCK-* rows.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if not tenant:
            raise CommandError(f"Tenant id={options['tenant_id']} not found.")

        today = timezone.localdate()
        props = {
            p.slug: p
            for p in Property.objects.filter(tenant=tenant, slug__in=("demo", "channex-demo"))
        }
        if "demo" not in props:
            raise CommandError("Property slug=demo not found on tenant.")

        units_by_code: dict[str, Unit] = {
            u.code: u
            for u in Unit.objects.filter(tenant=tenant, property__slug__in=props.keys())
        }

        refreshed = self._refresh_existing_guests(tenant)
        self.stdout.write(f"Refreshed guests on existing reservations: {refreshed}")

        if options["only_refresh_guests"]:
            self.stdout.write(self.style.SUCCESS("Done (guest refresh only)."))
            return

        seeds = self._build_seed_specs(today, props, units_by_code)
        created = updated = 0
        for spec in seeds:
            _, was_created = self._upsert_reservation(tenant, spec)
            if was_created:
                created += 1
            else:
                updated += 1

        total = Reservation.objects.filter(tenant=tenant).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Mock reservations: {created} created, {updated} updated. "
                f"Tenant total reservations: {total}"
            )
        )

    def _refresh_existing_guests(self, tenant: Tenant) -> int:
        count = 0
        reservations = list(
            Reservation.objects.filter(tenant=tenant).prefetch_related("guests")
        )
        for idx, reservation in enumerate(reservations):
            if reservation.import_source == "channex":
                self._refresh_channex_guests(tenant, reservation)
                count += reservation.guests.count()
                continue

            profile = GUEST_PROFILES[idx % len(GUEST_PROFILES)]
            first, last, nat, booker_country, domain = profile
            full_name = f"{first} {last}".strip()
            email = f"{first.lower()}.{last.lower().replace(' ', '')}@{domain}"

            reservation.booker_name = full_name
            reservation.booker_email = email
            reservation.booker_phone = f"+38591{7000000 + idx:07d}"[-12:]
            reservation.booker_country = booker_country
            reservation.booker_address = self._mock_address(booker_country)
            reservation.save(
                update_fields=[
                    "booker_name",
                    "booker_email",
                    "booker_phone",
                    "booker_country",
                    "booker_address",
                    "updated_at",
                ]
            )

            guests = list(reservation.guests.order_by("-is_primary", "id"))
            if not guests:
                Guest.objects.create(
                    tenant=tenant,
                    reservation=reservation,
                    first_name=first,
                    last_name=last,
                    name=full_name,
                    email=email,
                    nationality=nat,
                    document_country_iso2=nat,
                    is_primary=True,
                )
                count += 1
                continue

            for g_idx, guest in enumerate(guests):
                g_first, g_last, g_nat, _, g_domain = GUEST_PROFILES[
                    (idx + g_idx) % len(GUEST_PROFILES)
                ]
                guest.first_name = g_first
                guest.last_name = g_last
                guest.name = f"{g_first} {g_last}".strip()
                guest.email = (
                    f"{g_first.lower()}.{g_last.lower().replace(' ', '')}@{g_domain}"
                )
                guest.nationality = g_nat
                guest.document_country_iso2 = g_nat
                guest.document_country = g_nat
                guest.is_primary = g_idx == 0
                guest.save()
                count += 1

        return count

    def _refresh_channex_guests(self, tenant: Tenant, reservation: Reservation) -> None:
        """Channex cert rows: restore known test identity + HR country."""
        if reservation.booking_code == "TEST-STAY-001":
            first, last = "Ante", "Vrcan"
        else:
            guest = reservation.guests.first()
            if guest and guest.first_name:
                first, last = guest.first_name, guest.last_name
            else:
                first, last = "Ante", "Vrcan"

        full_name = f"{first} {last}".strip()
        reservation.booker_name = full_name
        reservation.booker_email = reservation.booker_email or "ante.vrcan@example.hr"
        reservation.booker_country = "HR"
        reservation.booker_address = self._mock_address("HR")
        reservation.save(
            update_fields=[
                "booker_name",
                "booker_email",
                "booker_country",
                "booker_address",
                "updated_at",
            ]
        )
        for guest in reservation.guests.all():
            guest.first_name = first
            guest.last_name = last
            guest.name = full_name
            guest.nationality = "HR"
            guest.document_country_iso2 = "HR"
            guest.document_country = "HR"
            guest.is_primary = True
            guest.save()

    def _build_seed_specs(
        self,
        today: date,
        props: dict[str, Property],
        units_by_code: dict[str, Unit],
    ) -> list[dict]:
        demo = props["demo"]
        channex = props.get("channex-demo")

        def d(offset: int) -> date:
            return today + timedelta(days=offset)

        specs: list[dict] = [
            {
                "booking_code": f"{MOCK_BOOKING_PREFIX}001",
                "property": demo,
                "unit_code": "STD-01",
                "status": Reservation.Status.CHECKED_IN,
                "check_in": d(-1),
                "check_out": d(2),
                "amount": Decimal("189.00"),
                "source": "Booking.com",
                "profile_idx": 1,
            },
            {
                "booking_code": f"{MOCK_BOOKING_PREFIX}002",
                "property": demo,
                "unit_code": "STD-02",
                "status": Reservation.Status.EXPECTED,
                "check_in": d(0),
                "check_out": d(3),
                "amount": Decimal("210.50"),
                "source": "Direct",
                "profile_idx": 2,
            },
            {
                "booking_code": f"{MOCK_BOOKING_PREFIX}003",
                "property": demo,
                "unit_code": "APT-01",
                "status": Reservation.Status.EXPECTED,
                "check_in": d(5),
                "check_out": d(8),
                "amount": Decimal("420.00"),
                "source": "Airbnb",
                "profile_idx": 3,
                "extra_guests": 1,
            },
            {
                "booking_code": f"{MOCK_BOOKING_PREFIX}004",
                "property": demo,
                "unit_code": "STD-01",
                "status": Reservation.Status.CHECKED_OUT,
                "check_in": d(-5),
                "check_out": d(-2),
                "amount": Decimal("156.00"),
                "source": "Direct",
                "profile_idx": 4,
            },
            {
                "booking_code": f"{MOCK_BOOKING_PREFIX}005",
                "property": demo,
                "unit_code": "STD-02",
                "status": Reservation.Status.EXPECTED,
                "check_in": d(10),
                "check_out": d(14),
                "amount": Decimal("298.00"),
                "source": "Expedia",
                "profile_idx": 5,
            },
            {
                "booking_code": f"{MOCK_BOOKING_PREFIX}006",
                "property": demo,
                "unit_code": "APT-01",
                "status": Reservation.Status.CANCELED,
                "check_in": d(2),
                "check_out": d(5),
                "amount": Decimal("0.00"),
                "source": "Booking.com",
                "profile_idx": 7,
            },
            {
                "booking_code": f"{MOCK_BOOKING_PREFIX}007",
                "property": demo,
                "unit_code": "STD-01",
                "status": Reservation.Status.EXPECTED,
                "check_in": d(18),
                "check_out": d(22),
                "amount": Decimal("340.00"),
                "source": "Direct",
                "profile_idx": 8,
            },
        ]

        if channex:
            specs.extend(
                [
                    {
                        "booking_code": f"{MOCK_BOOKING_PREFIX}008",
                        "property": channex,
                        "unit_code": "BCOM-STUDIO",
                        "status": Reservation.Status.EXPECTED,
                        "check_in": d(1),
                        "check_out": d(4),
                        "amount": Decimal("275.00"),
                        "currency": "GBP",
                        "source": "Booking.com",
                        "profile_idx": 9,
                    },
                    {
                        "booking_code": f"{MOCK_BOOKING_PREFIX}009",
                        "property": channex,
                        "unit_code": "BCOM-HOLIDAY",
                        "status": Reservation.Status.CHECKED_IN,
                        "check_in": d(-2),
                        "check_out": d(1),
                        "amount": Decimal("510.00"),
                        "currency": "GBP",
                        "source": "Booking.com",
                        "profile_idx": 10,
                    },
                    {
                        "booking_code": f"{MOCK_BOOKING_PREFIX}010",
                        "property": channex,
                        "unit_code": "BCOM-STUDIO",
                        "status": Reservation.Status.EXPECTED,
                        "check_in": d(7),
                        "check_out": d(12),
                        "amount": Decimal("620.00"),
                        "currency": "GBP",
                        "source": "Channex",
                        "profile_idx": 11,
                    },
                ]
            )

        for spec in specs:
            unit = units_by_code.get(spec["unit_code"])
            if not unit:
                raise CommandError(f"Unit code {spec['unit_code']!r} not found on tenant.")
            spec["unit"] = unit

        return specs

    def _upsert_reservation(self, tenant: Tenant, spec: dict) -> tuple[Reservation, bool]:
        nights = (spec["check_out"] - spec["check_in"]).days
        currency = spec.get("currency", "EUR")
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
            "currency": currency,
            "source": spec["source"],
            "import_source": "",
            "units_count": 1,
            "persons_count": 1 + spec.get("extra_guests", 0),
            "adults_count": 1 + spec.get("extra_guests", 0),
            "nights_count": max(nights, 0),
            "payment_status": "paid" if spec["status"] != Reservation.Status.CANCELED else "",
            "booked_at": timezone.now(),
        }
        if spec["status"] == Reservation.Status.CANCELED:
            defaults["canceled_at"] = timezone.now()

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
            defaults={
                "unit": unit,
                "room_name": unit.name,
                "amount": spec["amount"],
            },
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
        for extra in range(spec.get("extra_guests", 0)):
            g_first, g_last, g_nat, _, g_domain = GUEST_PROFILES[
                (spec["profile_idx"] + extra + 1) % len(GUEST_PROFILES)
            ]
            Guest.objects.create(
                tenant=tenant,
                reservation=reservation,
                first_name=g_first,
                last_name=g_last,
                name=f"{g_first} {g_last}".strip(),
                email=f"{g_first.lower()}.{g_last.lower()}@{g_domain}",
                nationality=g_nat,
                document_country_iso2=g_nat,
                document_country=g_nat,
                is_primary=False,
            )

        return reservation, created

    @staticmethod
    def _mock_address(country: str) -> str:
        addresses = {
            "HR": "Ilica 42, 10000 Zagreb",
            "DE": "Hauptstraße 12, 10115 Berlin",
            "AT": "Mariahilfer Straße 8, 1060 Wien",
            "IT": "Via Roma 15, 20121 Milano",
            "GB": "221B Baker Street, London",
            "US": "350 Fifth Avenue, New York, NY",
            "FR": "10 Rue de Rivoli, 75001 Paris",
            "SI": "Slovenska cesta 1, 1000 Ljubljana",
            "ES": "Calle Mayor 3, 28013 Madrid",
            "NL": "Damrak 1, 1012 LG Amsterdam",
            "CH": "Bahnhofstrasse 1, 8001 Zürich",
            "IE": "Grafton Street 10, Dublin",
            "SE": "Drottninggatan 5, 111 51 Stockholm",
        }
        return addresses.get(country, f"Demo address, {country}")
