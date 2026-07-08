"""Run daily ops collectors and aggregate results."""

from __future__ import annotations

import os
import socket
import time
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.core.daily_ops_report.collectors import COLLECTORS
from apps.core.daily_ops_report.types import DailyOpsReportResult, MetricResult, max_severity

ZAGREB = ZoneInfo("Europe/Zagreb")


def _reporter_process() -> str:
    return f"celery-worker (pid {os.getpid()})"


def _git_sha() -> str:
    return os.environ.get("STAY_GIT_SHA", "unknown")


def run_collectors() -> DailyOpsReportResult:
    start = time.perf_counter()
    generated_at = timezone.now().astimezone(ZAGREB)
    sections = []
    metrics: dict[str, MetricResult] = {}

    for collector in COLLECTORS:
        section = collector.collect()
        sections.append(section)
        for row in section.rows:
            metrics[row.key] = row

    duration_ms = int((time.perf_counter() - start) * 1000)
    overall = max_severity(*(section.severity for section in sections))

    return DailyOpsReportResult(
        sections=sections,
        overall_severity=overall,
        duration_ms=duration_ms,
        generated_at_iso=generated_at.isoformat(),
        reporter_process=_reporter_process(),
        git_sha=_git_sha(),
        hostname=socket.gethostname(),
        metrics=metrics,
    )
