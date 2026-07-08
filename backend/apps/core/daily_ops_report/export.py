"""JSON export for daily ops report."""

from __future__ import annotations

import json

from apps.core.daily_ops_report.types import DailyOpsReportResult, MetricResult, Severity

SCHEMA_VERSION = 1


def export_json(report: DailyOpsReportResult) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": report.generated_at_iso,
        "git_sha": report.git_sha,
        "hostname": report.hostname,
        "reporter_process": report.reporter_process,
        "duration_ms": report.duration_ms,
        "overall_severity": str(report.overall_severity),
        "sections": [
            {
                "title": section.title,
                "severity": str(section.severity),
                "summary": section.summary,
                "rows": [
                    {
                        "key": row.key,
                        "value": row.value,
                        "status": str(row.status),
                        "display": row.display,
                    }
                    for row in section.rows
                ],
            }
            for section in report.sections
        ],
        "metrics": {
            key: {
                "value": metric.value,
                "status": str(metric.status),
                "display": metric.display,
            }
            for key, metric in report.metrics.items()
        },
    }


def export_json_text(report: DailyOpsReportResult) -> str:
    return json.dumps(export_json(report), indent=2, sort_keys=True) + "\n"


def metrics_from_snapshot(snapshot: dict | None) -> dict[str, MetricResult]:
    if not snapshot:
        return {}
    raw = snapshot.get("metrics") or {}
    result: dict[str, MetricResult] = {}
    for key, item in raw.items():
        if not isinstance(item, dict):
            continue
        status_raw = item.get("status", Severity.OK)
        try:
            status = Severity(str(status_raw))
        except ValueError:
            status = Severity.OK
        result[key] = MetricResult(
            key=key,
            value=item.get("value"),
            status=status,
            display=str(item.get("display", "")),
        )
    return result
