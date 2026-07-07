from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.reservations.reports.delivery import deliver_property_financial_report_email
from apps.reservations.reports.property_financial_report import build_property_financial_report
from apps.reservations.reports.recipients import parse_financial_report_recipients
from apps.reservations.reports.types import PropertyFinancialReportParams, PropertyFinancialReportParamsError
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Build and email a property financial report (PDF + Excel attachments)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", required=True, help="Tenant slug, e.g. uzorita")
        parser.add_argument("--property-slug", required=True, help="Property slug, e.g. uzorita")
        parser.add_argument("--check-out-from", required=True, help="Inclusive lower bound YYYY-MM-DD")
        parser.add_argument("--check-out-to", required=True, help="Inclusive upper bound YYYY-MM-DD")
        parser.add_argument("--recipient", required=True, help="Recipient email address")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build report and print summary without sending email.",
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            raise CommandError(f"Tenant slug={options['tenant_slug']!r} not found.")

        try:
            params = PropertyFinancialReportParams.from_query(
                tenant,
                property_slug=options["property_slug"],
                check_out_from=options["check_out_from"],
                check_out_to=options["check_out_to"],
            )
        except PropertyFinancialReportParamsError as exc:
            raise CommandError(exc.code) from exc

        result = build_property_financial_report(params)
        self.stdout.write(
            f"Report: {result.meta.property_name} · "
            f"{result.meta.check_out_from} – {result.meta.check_out_to} · "
            f"{result.totals.reservation_count} reservations · "
            f"net {result.totals.net} {result.meta.currency}"
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — email not sent."))
            return

        outcome = deliver_property_financial_report_email(
            params,
            recipients=parse_financial_report_recipients(options["recipient"]),
        )
        if outcome.get("status") != "sent":
            raise CommandError(f"Email not sent: {outcome.get('reason', 'unknown')}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent to {', '.join(outcome['recipients'])}: {outcome.get('subject', '')}"
            )
        )
