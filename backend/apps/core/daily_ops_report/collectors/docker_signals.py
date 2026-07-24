"""Experimental docker log signals (host-generated JSON)."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings

from apps.core.daily_ops_report.types import MetricResult, ReportSection, Severity, max_severity

_DOCKER_SIGNALS_REL = Path("ops") / "daily_ops_report" / "docker_signals.json"
_HELP = (
    "Run ./scripts/collect-docker-gunicorn-signals.sh on host "
    "(Experimental — host-dependent)."
)


def docker_signals_path() -> Path:
    return Path(settings.MEDIA_ROOT) / _DOCKER_SIGNALS_REL


class DockerSignalsCollector:
    title = "Docker signals (Experimental)"

    def collect(self) -> ReportSection:
        path = docker_signals_path()
        if not path.is_file():
            rows = [
                MetricResult(
                    key="docker.worker_timeout_count",
                    value=None,
                    status=Severity.WARN,
                    display="missing file",
                ),
                MetricResult(
                    key="docker.sse_stream_opened",
                    value=None,
                    status=Severity.WARN,
                    display="missing file",
                ),
                MetricResult(
                    key="docker.sse_stream_closed",
                    value=None,
                    status=Severity.WARN,
                    display="missing file",
                ),
                MetricResult(
                    key="docker.sse_invariant_breach",
                    value=None,
                    status=Severity.WARN,
                    display="missing file",
                ),
            ]
            return ReportSection(
                title=self.title,
                severity=Severity.WARN,
                rows=rows,
                summary=f"File not found: {path}. {_HELP}",
            )

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rows = [
                MetricResult(
                    key="docker.worker_timeout_count",
                    value=None,
                    status=Severity.WARN,
                    display="invalid JSON",
                ),
            ]
            return ReportSection(
                title=self.title,
                severity=Severity.WARN,
                rows=rows,
                summary=f"Could not parse {path}. {_HELP}",
            )

        metrics = payload.get("metrics") or payload
        rows: list[MetricResult] = []

        timeout_count = int(metrics.get("worker_timeout_count", 0))
        timeout_status = Severity.WARN if timeout_count > 0 else Severity.OK
        rows.append(
            MetricResult(
                key="docker.worker_timeout_count",
                value=timeout_count,
                status=timeout_status,
                display=str(timeout_count),
            )
        )

        for key, json_key in (
            ("docker.sse_stream_opened", "sse_stream_opened"),
            ("docker.sse_stream_closed", "sse_stream_closed"),
        ):
            value = int(metrics.get(json_key, 0))
            rows.append(
                MetricResult(
                    key=key,
                    value=value,
                    status=Severity.OK,
                    display=str(value),
                )
            )

        # Permanent SSE lifecycle instrumentation (ADR 0005): any sse_invariant_breach
        # in container logs is CRIT — keep through Redis/Uvicorn phases.
        breach_count = int(metrics.get("sse_invariant_breach", 0))
        breach_status = Severity.CRIT if breach_count > 0 else Severity.OK
        rows.append(
            MetricResult(
                key="docker.sse_invariant_breach",
                value=breach_count,
                status=breach_status,
                display=str(breach_count),
            )
        )

        generated_at = payload.get("generated_at", "unknown")
        summary = f"Host file {path.name}, generated_at={generated_at}. Experimental — host-dependent."

        return ReportSection(
            title=self.title,
            severity=max_severity(*(row.status for row in rows)),
            rows=rows,
            summary=summary,
        )
