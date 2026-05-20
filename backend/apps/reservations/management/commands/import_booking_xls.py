from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from apps.properties.models import Property
from apps.reservations.booking_xls_import import import_booking_xls_file, parse_booking_xls
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Import Booking.com .xls export into stay.hr reservations (tenant-scoped)."

    def add_arguments(self, parser):
        parser.add_argument(
            "xls_path",
            type=str,
            help="Path to Booking .xls export (Excel 97–2003).",
        )
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=2,
            help="Tenant primary key (default: 2 = uzorita).",
        )
        parser.add_argument(
            "--property-slug",
            type=str,
            default="uzorita",
            help="Property slug on tenant (default: uzorita).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse only; print row actions without writing.",
        )
        parser.add_argument(
            "--check-in-from",
            type=str,
            default="",
            help="Only import rows with check-in on/after YYYY-MM-DD.",
        )
        parser.add_argument(
            "--check-in-to",
            type=str,
            default="",
            help="Only import rows with check-in on/before YYYY-MM-DD.",
        )
        parser.add_argument(
            "--allow-update",
            action="store_true",
            help="Update reservations that already exist (default: skip existing).",
        )

    def handle(self, *args, **options):
        path = Path(options["xls_path"]).expanduser()
        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if tenant is None:
            raise CommandError(f"Tenant id={options['tenant_id']} not found.")

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        if prop is None:
            raise CommandError(
                f"Property slug={options['property_slug']!r} not found on tenant {tenant.slug}."
            )

        check_in_from = self._parse_date_option(options["check_in_from"], "--check-in-from")
        check_in_to = self._parse_date_option(options["check_in_to"], "--check-in-to")
        if check_in_from is None and check_in_to is None:
            inferred = self._infer_range_from_filename(path.name)
            check_in_from, check_in_to = inferred if inferred else (None, None)

        rows = parse_booking_xls(str(path))
        self.stdout.write(f"Parsed {len(rows)} row(s) from {path.name}")

        if check_in_from or check_in_to:
            before = len(rows)
            rows = [
                r
                for r in rows
                if (not check_in_from or r.check_in_date >= check_in_from)
                and (not check_in_to or r.check_in_date <= check_in_to)
            ]
            self.stdout.write(
                f"Filtered by check-in {check_in_from or '…'} – {check_in_to or '…'}: "
                f"{len(rows)} of {before}"
            )

        if not rows:
            self.stdout.write(self.style.WARNING("No rows to import."))
            return

        for row in rows:
            self.stdout.write(
                f"  {row.external_id} | {row.booker_name} | "
                f"{row.check_in_date} → {row.check_out_date} | {row.room_name}"
            )

        skip_existing = not options["allow_update"]
        if skip_existing:
            self.stdout.write(
                "Mode: skip existing reservations (only new Booking numbers are imported)."
            )

        stats = import_booking_xls_file(
            str(path),
            tenant=tenant,
            property=prop,
            dry_run=options["dry_run"],
            check_in_from=check_in_from,
            check_in_to=check_in_to,
            skip_existing=skip_existing,
        )

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run: {stats}"))
            return

        if stats["errors"]:
            for err in stats["errors"]:
                self.stderr.write(f"{err['external_id']}: {err['error']}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Import done: created={stats['created']} skipped={stats['skipped']} "
                f"updated={stats['updated']} errors={len(stats['errors'])} total={stats['total']}"
            )
        )

    def _parse_date_option(self, raw: str, flag: str) -> date | None:
        value = (raw or "").strip()
        if not value:
            return None
        parsed = parse_date(value)
        if parsed is None:
            raise CommandError(f"Invalid date for {flag}: {value!r} (use YYYY-MM-DD)")
        return parsed

    def _infer_range_from_filename(self, name: str) -> tuple[date | None, date | None] | None:
        """Booking export names like 'Reservation 2026-05-20 to 2026-05-21.xls'."""
        match = re.search(
            r"(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})",
            name,
            re.IGNORECASE,
        )
        if not match:
            return None
        start = parse_date(match.group(1))
        end = parse_date(match.group(2))
        if start is None or end is None:
            return None
        return (start, end)
