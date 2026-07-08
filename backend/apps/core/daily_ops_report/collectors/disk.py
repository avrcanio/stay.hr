"""Disk usage for MEDIA_ROOT."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings

from apps.core.daily_ops_report.types import MetricResult, ReportSection, Severity, max_severity


class DiskCollector:
    title = "Disk"

    def collect(self) -> ReportSection:
        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(media_root)
        total_gb = round(usage.total / (1024**3), 2)
        used_gb = round(usage.used / (1024**3), 2)
        free_gb = round(usage.free / (1024**3), 2)
        used_pct = round(usage.used / usage.total * 100, 1) if usage.total else 0.0

        warn_pct = int(getattr(settings, "DAILY_OPS_REPORT_DISK_WARN_PCT", 85))
        crit_pct = int(getattr(settings, "DAILY_OPS_REPORT_DISK_CRIT_PCT", 95))

        if used_pct >= crit_pct:
            pct_status = Severity.CRIT
        elif used_pct >= warn_pct:
            pct_status = Severity.WARN
        else:
            pct_status = Severity.OK

        rows = [
            MetricResult(
                key="disk.total_gb",
                value=total_gb,
                status=Severity.OK,
                display=f"{total_gb} GB",
            ),
            MetricResult(
                key="disk.used_gb",
                value=used_gb,
                status=Severity.OK,
                display=f"{used_gb} GB",
            ),
            MetricResult(
                key="disk.free_gb",
                value=free_gb,
                status=Severity.OK,
                display=f"{free_gb} GB",
            ),
            MetricResult(
                key="disk.used_pct",
                value=used_pct,
                status=pct_status,
                display=f"{used_pct}%",
            ),
        ]

        section_severity = max_severity(*(row.status for row in rows))
        summary = f"MEDIA_ROOT={media_root}"

        return ReportSection(
            title=self.title,
            severity=section_severity,
            rows=rows,
            summary=summary,
        )
