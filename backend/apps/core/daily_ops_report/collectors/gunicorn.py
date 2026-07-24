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

        # Permanent SSE lifecycle instrumentation (ADR 0005): keep through Redis/Uvicorn.
        # opened − closed − active == 0
        invariant_delta = int(sse.get("invariant_delta") or 0)
        invariant_ok = bool(sse.get("invariant_ok", invariant_delta == 0))
        invariant_status = Severity.OK if invariant_ok and invariant_delta == 0 else Severity.CRIT
        rows.append(
            MetricResult(
                key="sse.invariant_delta",
                value=invariant_delta,
                status=invariant_status,
                display=f"{invariant_delta} (reporter process)",
            )
        )
        rows.append(
            MetricResult(
                key="sse.invariant_ok",
                value=1 if invariant_ok else 0,
                status=invariant_status,
                display="true" if invariant_ok else "false",
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

        event_bus = payload.get("event_bus") or {}
        bus_backend = str(event_bus.get("backend") or "in_process")
        rows.append(
            MetricResult(
                key="event_bus.backend",
                value=bus_backend,
                status=Severity.OK,
                display=bus_backend,
            )
        )
        reconnect = int(event_bus.get("redis_reconnect_count") or 0)
        reconnect_status = Severity.OK
        if bus_backend == "redis" and reconnect > 0:
            reconnect_status = Severity.WARN
        rows.append(
            MetricResult(
                key="event_bus.redis_reconnect_count",
                value=reconnect,
                status=reconnect_status,
                display=str(reconnect),
            )
        )
        for counter_key in (
            "publish_count",
            "receive_count",
            "local_fallback_count",
            "dedupe_drop_count",
        ):
            numeric = int(event_bus.get(counter_key) or 0)
            status = Severity.OK
            if counter_key == "local_fallback_count" and numeric > 0:
                status = Severity.WARN
            rows.append(
                MetricResult(
                    key=f"event_bus.{counter_key}",
                    value=numeric,
                    status=status,
                    display=f"{numeric} (reporter process)",
                )
            )
        last_fallback = event_bus.get("last_fallback_at")
        rows.append(
            MetricResult(
                key="event_bus.last_fallback_at",
                value=last_fallback,
                status=Severity.WARN if last_fallback else Severity.OK,
                display=str(last_fallback) if last_fallback else "null",
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
