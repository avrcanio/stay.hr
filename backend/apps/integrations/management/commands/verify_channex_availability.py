from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from apps.integrations.channex.availability_verify_service import (
    DEFAULT_VERIFY_DAYS,
    verify_and_repair_availability,
)

# Ops convenience default only — service requires an explicit tenant_slug.
OPS_DEFAULT_TENANT_SLUG = "uzorita"


class Command(BaseCommand):
    help = (
        "Verify stay.hr occupancy vs live Channex GET /availability; "
        "re-push ARI on mismatch (any Channex tenant; default slug: uzorita)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-slug",
            default=OPS_DEFAULT_TENANT_SLUG,
            help=f"Tenant slug (default: {OPS_DEFAULT_TENANT_SLUG}).",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_VERIFY_DAYS,
            help=f"Number of nights to verify from --from-date (default: {DEFAULT_VERIFY_DAYS}).",
        )
        parser.add_argument(
            "--from-date",
            type=str,
            default="",
            help="Start date YYYY-MM-DD (default: today).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report mismatches only; do not re-push or notify.",
        )

    def handle(self, *args, **options):
        from_date = self._parse_from_date(options["from_date"])
        dry_run = bool(options["dry_run"])
        result = verify_and_repair_availability(
            tenant_slug=options["tenant_slug"],
            days=options["days"],
            from_date=from_date,
            repair=not dry_run,
            notify=not dry_run,
        )

        if result.get("skipped"):
            self.stderr.write(
                self.style.ERROR(
                    f"Skipped: {result.get('reason')} (tenant={options['tenant_slug']})"
                )
            )
            raise SystemExit(2)

        mismatch_count = int(result.get("mismatch_count") or 0)
        repaired = int(result.get("repaired") or 0)
        self.stdout.write(
            f"Tenant {result.get('tenant_slug')} "
            f"{result.get('from_date')}..{result.get('to_date')}: "
            f"units={result.get('units_checked')} "
            f"mismatches={mismatch_count} repaired={repaired}"
        )
        for row in result.get("mismatches") or []:
            self.stdout.write(
                f"  {row['unit_code']} {row['day']}: "
                f"expected={row['expected']} channex={row['actual']}"
            )

        if mismatch_count:
            style = self.style.WARNING if dry_run else self.style.SUCCESS
            msg = (
                f"Found {mismatch_count} mismatch(es)"
                + (" (dry-run, not repaired)." if dry_run else f"; repaired={repaired}.")
            )
            self.stdout.write(style(msg))
            if dry_run:
                raise SystemExit(1)
            return

        self.stdout.write(self.style.SUCCESS("No availability mismatches."))

    @staticmethod
    def _parse_from_date(raw: str) -> date | None:
        if not raw:
            return None
        try:
            return date.fromisoformat(raw.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid --from-date {raw!r}; use YYYY-MM-DD.") from exc
