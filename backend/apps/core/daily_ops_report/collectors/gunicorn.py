"""Gunicorn + SSE metrics (reporter process scope)."""

from __future__ import annotations

import os

from django.conf import settings

from apps.core.daily_ops_report.types import MetricResult, ReportSection, Severity, max_severity
from apps.core.system_status import build_system_status_payload

_SSE_PEAK_WARN = 30
_EXPECTED_WORKERS = 8
_EXPECTED_TIMEOUT = 3600


class GunicornCollector:
    title = "Gunicorn + SSE"

    def collect(self) -> ReportSection:
        reporter = f"celery-worker (pid {os.getpid()})"
        payload = build_system_status_payload(reporter_process=reporter)
        gunicorn = payload["gunicorn"]
        sse = payload["sse"]
        build = payload["build"]

        rows: list[MetricResult] = []

        workers = int(gunicorn.get("workers", _EXPECTED_WORKERS))
        workers_status = Severity.OK if workers == _EXPECTED_WORKERS else Severity.WARN
        rows.append(
            MetricResult(
                key="gunicorn.workers",
                value=workers,
                status=workers_status,
                display=str(workers),
            )
        )

        timeout = int(gunicorn.get("timeout", _EXPECTED_TIMEOUT))
        timeout_status = Severity.OK if timeout == _EXPECTED_TIMEOUT else Severity.WARN
        rows.append(
            MetricResult(
                key="gunicorn.timeout",
                value=timeout,
                status=timeout_status,
                display=f"{timeout}s",
            )
        )

        git_sha = str(build.get("git_sha", "unknown"))
        rows.append(
            MetricResult(
                key="gunicorn.git_sha",
                value=git_sha,
                status=Severity.OK,
                display=git_sha,
            )
        )

        uptime = int(gunicorn.get("uptime_seconds", 0))
        rows.append(
            MetricResult(
                key="gunicorn.uptime_seconds",
                value=uptime,
                status=Severity.OK,
                display=f"{uptime}s (reporter process)",
            )
        )

        for sse_key, display_suffix in (
            ("active_connections", "active"),
            ("peak_connections", "peak"),
            ("connections_opened_total", "opened"),
            ("connections_closed_total", "closed"),
        ):
            raw = sse.get(sse_key)
            numeric = int(raw) if raw is not None else 0
            status = Severity.OK
            if sse_key == "peak_connections" and numeric > _SSE_PEAK_WARN:
                status = Severity.WARN
            rows.append(
                MetricResult(
                    key=f"sse.{sse_key}",
                    value=numeric,
                    status=status,
                    display=f"{numeric} ({display_suffix}, reporter process)",
                )
            )

        avg_duration = sse.get("average_duration_seconds")
        avg_display = (
            f"{avg_duration}s (reporter process)"
            if avg_duration is not None
            else "N/A (reporter process)"
        )
        rows.append(
            MetricResult(
                key="sse.average_duration_seconds",
                value=avg_duration,
                status=Severity.OK,
                display=avg_display,
            )
        )

        section_severity = max_severity(*(row.status for row in rows))
        summary = (
            f"Reporter: {reporter}. SSE counters are per-process (see runbook); "
            "use Experimental docker signals for cross-worker Gunicorn logs."
        )
        if getattr(settings, "DEBUG", False):
            summary += " DEBUG=True."

        return ReportSection(
            title=self.title,
            severity=section_severity,
            rows=rows,
            summary=summary,
        )
