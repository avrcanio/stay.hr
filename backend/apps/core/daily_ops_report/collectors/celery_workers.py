"""Celery worker responsiveness."""

from __future__ import annotations

from django.conf import settings
from celery import current_app

from apps.core.daily_ops_report.types import MetricResult, ReportSection, Severity, max_severity


def _expected_services() -> list[str]:
    raw = getattr(settings, "DAILY_OPS_REPORT_CELERY_EXPECTED", "celery-worker,celery-beat")
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _service_responding(service: str, worker_names: set[str]) -> bool:
    normalized = service.replace("-", "_").lower()
    for worker in worker_names:
        worker_lower = worker.lower()
        if normalized in worker_lower or service.lower() in worker_lower:
            return True
    return False


class CeleryWorkersCollector:
    title = "Celery"

    def collect(self) -> ReportSection:
        expected = _expected_services()
        try:
            ping_results = current_app.control.ping(timeout=2.0) or []
        except Exception:
            ping_results = []

        worker_names: set[str] = set()
        for reply in ping_results:
            worker_names.update(reply.keys())

        actual = len(worker_names)
        found_services = [svc for svc in expected if _service_responding(svc, worker_names)]
        missing = sorted(set(expected) - set(found_services))

        if missing:
            status = Severity.WARN
        elif actual == 0:
            status = Severity.CRIT
        else:
            status = Severity.OK

        display_missing = ", ".join(missing) if missing else "none"
        summary_display = (
            f"Expected: {len(expected)}, Actual: {actual}, Missing: {display_missing}"
        )

        rows = [
            MetricResult(
                key="celery.expected",
                value=len(expected),
                status=Severity.OK,
                display=str(len(expected)),
            ),
            MetricResult(
                key="celery.actual",
                value=actual,
                status=status,
                display=str(actual),
            ),
            MetricResult(
                key="celery.missing",
                value=display_missing,
                status=status,
                display=display_missing,
            ),
        ]

        return ReportSection(
            title=self.title,
            severity=max_severity(*(row.status for row in rows)),
            rows=rows,
            summary=summary_display,
        )
