"""Database connectivity and migration checks."""

from __future__ import annotations

import math
import time

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.core.daily_ops_report.types import MetricResult, ReportSection, Severity, max_severity


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct / 100.0
    floor_k = math.floor(k)
    ceil_k = math.ceil(k)
    if floor_k == ceil_k:
        return sorted_values[int(k)]
    return sorted_values[floor_k] * (ceil_k - k) + sorted_values[ceil_k] * (k - floor_k)


def _migrations_pending() -> bool:
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    return bool(executor.migration_plan(targets))


class DbCollector:
    title = "Database"

    def collect(self) -> ReportSection:
        sample_count = max(1, int(getattr(settings, "DAILY_OPS_REPORT_DB_SAMPLES", 50)))
        latencies_ms: list[float] = []

        for _ in range(sample_count):
            start = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            latencies_ms.append((time.perf_counter() - start) * 1000.0)

        latencies_ms.sort()
        ping_ms = round(latencies_ms[0], 2) if latencies_ms else None
        p50 = _percentile(latencies_ms, 50)
        p95 = _percentile(latencies_ms, 95)

        ping_status = Severity.OK
        if p95 is not None and p95 > 500:
            ping_status = Severity.WARN

        pending = _migrations_pending()
        migration_status = Severity.CRIT if pending else Severity.OK

        rows = [
            MetricResult(
                key="db.ping_ms",
                value=ping_ms,
                status=ping_status,
                display=f"{ping_ms} ms" if ping_ms is not None else "—",
            ),
            MetricResult(
                key="db.p50_ms",
                value=round(p50, 2) if p50 is not None else None,
                status=ping_status,
                display=f"{round(p50, 2)} ms" if p50 is not None else "—",
            ),
            MetricResult(
                key="db.p95_ms",
                value=round(p95, 2) if p95 is not None else None,
                status=ping_status,
                display=f"{round(p95, 2)} ms" if p95 is not None else "—",
            ),
            MetricResult(
                key="migrations.pending",
                value=pending,
                status=migration_status,
                display="yes" if pending else "no",
            ),
        ]

        section_severity = max_severity(*(row.status for row in rows))
        summary = f"{sample_count} SELECT 1 samples; p95 WARN threshold 500 ms."

        return ReportSection(
            title=self.title,
            severity=section_severity,
            rows=rows,
            summary=summary,
        )
