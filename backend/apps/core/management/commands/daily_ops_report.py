from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.daily_ops_report.export import export_json_text
from apps.core.daily_ops_report.format import format_markdown
from apps.core.daily_ops_report.orchestrator import run_collectors
from apps.core.daily_ops_report.snapshot import load_previous_metrics
from apps.core.daily_ops_report.tasks import run_daily_ops_report


class Command(BaseCommand):
    help = "Collect daily ops metrics, write snapshot/Markdown, optionally email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--print-markdown",
            action="store_true",
            help="Print Markdown to stdout only (no email, no file writes).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print JSON collector output to stdout.",
        )
        parser.add_argument(
            "--write-only",
            action="store_true",
            help="Write Markdown + snapshot without sending email.",
        )
        parser.add_argument(
            "--no-email",
            action="store_true",
            help="Write files but skip email.",
        )

    def handle(self, *args, **options):
        if options.get("print_markdown"):
            report = run_collectors()
            previous = load_previous_metrics()
            self.stdout.write(format_markdown(report, previous_metrics=previous))
            return

        if options.get("json"):
            report = run_collectors()
            self.stdout.write(export_json_text(report))
            return

        send_email = not options["write_only"] and not options["no_email"]
        result = run_daily_ops_report(send_email=send_email, write_files=True)
        self.stdout.write(result["markdown"])

        if send_email:
            if result.get("sent"):
                self.stdout.write(self.style.SUCCESS("Email sent."))
            else:
                reason = result.get("reason", "send_failed")
                self.stdout.write(self.style.WARNING(f"Email not sent: {reason}"))
