from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.reservations.document_intake_report_snapshot import (
    load_report_snapshot,
    report_snapshot_path,
    save_report_snapshot,
    should_send_report_today,
)
from apps.reservations.document_intake_telemetry import (
    QUALITY_MODEL_ID,
    _format_health_section,
    _format_metric_delta,
    format_report_email_subject,
    format_telemetry_report,
    load_document_intake_quality_kpis,
)
from apps.reservations.document_intake_telemetry_tasks import (
    send_document_intake_quality_report,
)
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobStatus
from apps.tenants.models import Tenant

ZAGREB = ZoneInfo("Europe/Zagreb")


def _sample_kpis(**overrides) -> dict:
    base = {
        "processed": 10,
        "done_count": 9,
        "failed_count": 1,
        "missing_telemetry": 0,
        "quality_stats": {"mean": 84.1, "median": 85.0, "p10": 70.0, "p90": 95.0},
        "auto_apply_rate": 0.78,
        "unknown_person_rate": 0.024,
        "ocr_under_extracted_rate": 0.051,
        "top_reasons": [("no_mrz", 5), ("unknown_person", 2)],
        "tenant_mismatch": 0,
    }
    base.update(overrides)
    return base


@override_settings(
    MEDIA_ROOT="/tmp/stay-test-media",
    DOCUMENT_INTAKE_REPORT_SNAPSHOT_PATH="",
)
class DocumentIntakeReportSnapshotTests(TestCase):
    def setUp(self):
        path = report_snapshot_path()
        if path.exists():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)

    def test_snapshot_save_load_roundtrip(self):
        kpis = _sample_kpis()
        save_report_snapshot(kpis=kpis, lookback_days=1, send_every_days=1)
        loaded = load_report_snapshot()
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["lookback_days"], 1)
        self.assertEqual(loaded["kpis"]["processed"], 10)
        self.assertEqual(
            [tuple(item) for item in loaded["top_reasons"]],
            kpis["top_reasons"],
        )

        save_report_snapshot(kpis=kpis, lookback_days=2, send_every_days=2)
        reloaded = load_report_snapshot()
        assert reloaded is not None
        self.assertEqual(reloaded["lookback_days"], 2)

    def test_should_send_respects_interval(self):
        yesterday = timezone.now().astimezone(ZAGREB).date() - timedelta(days=1)
        snapshot = {
            "generated_at": datetime(
                yesterday.year, yesterday.month, yesterday.day, 9, 0, tzinfo=ZAGREB
            ).isoformat(),
        }
        today = yesterday + timedelta(days=1)
        should_send, reason = should_send_report_today(
            snapshot=snapshot,
            send_every_days=2,
            monday_only=False,
            today=today,
        )
        self.assertFalse(should_send)
        self.assertIn("interval_not_elapsed", reason)

    def test_should_send_when_no_snapshot(self):
        should_send, reason = should_send_report_today(
            snapshot=None,
            send_every_days=7,
            monday_only=False,
            today=date(2026, 7, 6),
        )
        self.assertTrue(should_send)
        self.assertEqual(reason, "no_previous_snapshot")

    def test_should_send_monday_only(self):
        should_send, reason = should_send_report_today(
            snapshot=None,
            send_every_days=1,
            monday_only=True,
            today=date(2026, 7, 7),  # Tuesday
        )
        self.assertFalse(should_send)
        self.assertEqual(reason, "monday_only")


class DocumentIntakeReportFormatTests(TestCase):
    def test_format_health_section_ok(self):
        lines = _format_health_section(_sample_kpis(tenant_mismatch=0))
        self.assertTrue(any("OK (0)" in line for line in lines))
        self.assertTrue(any("100%" in line for line in lines))

    def test_format_health_section_alert(self):
        lines = _format_health_section(_sample_kpis(tenant_mismatch=3))
        self.assertTrue(any("ALERT (3)" in line for line in lines))

    def test_format_trends_delta(self):
        delta = _format_metric_delta(84.1, 82.3)
        self.assertEqual(delta, "▲ +1.8")

    def test_format_trends_delta_negative_percent(self):
        delta = _format_metric_delta(0.024, 0.031, as_percent=True)
        self.assertEqual(delta, "▼ -0.7%")

    def test_format_trends_section_in_email(self):
        previous = {
            "kpis": _sample_kpis(
                quality_stats={"mean": 82.3, "median": 83.0, "p10": 68.0, "p90": 93.0},
                unknown_person_rate=0.031,
                ocr_under_extracted_rate=0.063,
                auto_apply_rate=0.75,
            ),
            "top_reasons": [("no_mrz", 5)],
        }
        body = format_telemetry_report(
            _sample_kpis(),
            previous_snapshot=previous,
            for_email=True,
        )
        self.assertIn("Health", body)
        self.assertIn("Trends (vs previous report)", body)
        self.assertIn("▲ +1.8", body)
        self.assertIn("New reasons since previous report", body)

    def test_new_regression_reasons(self):
        previous = {
            "kpis": _sample_kpis(top_reasons=[("no_mrz", 5)]),
            "top_reasons": [("no_mrz", 5)],
        }
        current = _sample_kpis(top_reasons=[("no_mrz", 5), ("face_only", 1)])
        body = format_telemetry_report(current, previous_snapshot=previous, for_email=True)
        self.assertIn("+ face_only", body)

    def test_no_new_regression_reasons(self):
        previous = {
            "kpis": _sample_kpis(),
            "top_reasons": [("no_mrz", 5), ("unknown_person", 2)],
        }
        body = format_telemetry_report(_sample_kpis(), previous_snapshot=previous, for_email=True)
        self.assertIn("No new regression reasons.", body)

    def test_email_subject_format(self):
        subject = format_report_email_subject(days=1, report_date=date(2026, 7, 6))
        self.assertEqual(subject, "Stay.hr OCR Quality Report • 1 day • 2026-07-06")
        subject_plural = format_report_email_subject(days=7, report_date=date(2026, 7, 6))
        self.assertIn("7 days", subject_plural)

    def test_cli_format_excludes_email_sections(self):
        body = format_telemetry_report(_sample_kpis(), for_email=False)
        self.assertNotIn("Trends (vs previous report)", body)
        self.assertNotIn("Health", body)


class DocumentIntakeQualityKpisLoaderTests(TestCase):
    def test_load_document_intake_quality_kpis(self):
        tenant = Tenant.objects.create(name="Report KPI", slug="report-kpi")
        DocumentIntakeJob.objects.create(
            tenant=tenant,
            status=DocumentIntakeJobStatus.DONE,
            processed_at=timezone.now(),
            ocr_result={
                "_telemetry": {
                    "quality_model": QUALITY_MODEL_ID,
                    "pipeline_version": "document-intake-v1",
                    "quality_score": 80,
                    "summary_reasons": ["no_mrz"],
                    "persons": [{"reasons": []}],
                    "job_metrics": {
                        "auto_apply_count": 1,
                        "match_count": 1,
                        "unknown_person_count": 0,
                        "ocr_under_extracted": False,
                    },
                }
            },
        )
        kpis = load_document_intake_quality_kpis(days=7)
        self.assertEqual(kpis["processed"], 1)
        self.assertIn("quality_stats", kpis)
        self.assertIn("top_reasons", kpis)


@override_settings(
    MEDIA_ROOT="/tmp/stay-test-media-task",
    DOCUMENT_INTAKE_REPORT_SNAPSHOT_PATH="/tmp/stay-test-media-task/ops/snapshot.json",
    DOCUMENT_INTAKE_QUALITY_REPORT_ENABLED=False,
    DOCUMENT_INTAKE_QUALITY_REPORT_EMAIL="ops@example.com",
    EMAIL_HOST="mail.example.com",
)
class DocumentIntakeQualityReportTaskTests(TestCase):
    def setUp(self):
        path = Path("/tmp/stay-test-media-task/ops/snapshot.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()

    def test_send_report_skips_when_disabled(self):
        result = send_document_intake_quality_report()
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "disabled")

    @override_settings(DOCUMENT_INTAKE_QUALITY_REPORT_ENABLED=True)
    @patch(
        "apps.reservations.document_intake_telemetry_tasks.load_document_intake_quality_kpis",
        return_value=_sample_kpis(),
    )
    @patch(
        "apps.reservations.document_intake_telemetry_tasks.send_ops_report_email",
        return_value=True,
    )
    def test_send_report_saves_snapshot_on_success(self, mock_send, _mock_kpis):
        result = send_document_intake_quality_report()
        self.assertTrue(result["sent"])
        mock_send.assert_called_once()
        snapshot_path = Path("/tmp/stay-test-media-task/ops/snapshot.json")
        self.assertTrue(snapshot_path.is_file())
        data = json.loads(snapshot_path.read_text())
        self.assertEqual(data["kpis"]["processed"], 10)

    @override_settings(DOCUMENT_INTAKE_QUALITY_REPORT_ENABLED=True)
    @patch(
        "apps.reservations.document_intake_telemetry_tasks.load_document_intake_quality_kpis",
        return_value=_sample_kpis(),
    )
    @patch(
        "apps.reservations.document_intake_telemetry_tasks.send_ops_report_email",
        return_value=False,
    )
    def test_send_report_does_not_save_snapshot_on_failure(self, _mock_send, _mock_kpis):
        result = send_document_intake_quality_report()
        self.assertFalse(result["sent"])
        snapshot_path = Path("/tmp/stay-test-media-task/ops/snapshot.json")
        self.assertFalse(snapshot_path.exists())
