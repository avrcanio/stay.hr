from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.reservations.document_intake_telemetry import (
    QUALITY_MODEL_ID,
    format_telemetry_report,
    load_document_intake_quality_kpis,
)


class Command(BaseCommand):
    help = "Report document intake OCR quality KPIs from persisted _telemetry."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Look back N days from now (default: 7).",
        )
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=None,
            help="Optional tenant filter.",
        )
        parser.add_argument(
            "--quality-model",
            type=str,
            default=QUALITY_MODEL_ID,
            help=f"Filter jobs by quality_model (default: {QUALITY_MODEL_ID}).",
        )
        parser.add_argument(
            "--pipeline-version",
            type=str,
            default="",
            help="Optional pipeline_version filter.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON instead of plain text.",
        )

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        pipeline_version = (options.get("pipeline_version") or "").strip() or None
        quality_model = (options.get("quality_model") or "").strip() or None

        kpis = load_document_intake_quality_kpis(
            days=days,
            tenant_id=options.get("tenant_id"),
            quality_model=quality_model,
            pipeline_version=pipeline_version,
        )
        self.stdout.write(format_telemetry_report(kpis, as_json=bool(options.get("json"))))
