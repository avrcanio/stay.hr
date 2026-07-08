"""Markdown formatting for daily ops report."""

from __future__ import annotations

from apps.core.daily_ops_report.types import DailyOpsReportResult, MetricResult, Severity


def format_metric_delta(
    current: float | int | str | None,
    previous: float | int | str | None,
) -> str:
    if current is None or previous is None:
        return "—"
    try:
        cur = float(current)
        prev = float(previous)
    except (TypeError, ValueError):
        return "—"
    diff = cur - prev
    if diff == 0:
        return "0"
    sign = "+" if diff > 0 else ""
    if abs(diff) < 10 and "." in str(current):
        return f"{sign}{round(diff, 1)}"
    if float(diff).is_integer():
        return f"{sign}{int(diff)}"
    return f"{sign}{round(diff, 1)}"


def format_markdown(
    report: DailyOpsReportResult,
    *,
    previous_metrics: dict[str, MetricResult] | None = None,
) -> str:
    previous_metrics = previous_metrics or {}
    duration_s = round(report.duration_ms / 1000, 1)
    lines = [
        f"# Daily Ops Report [{report.overall_severity}]",
        "",
        f"Generated: {report.generated_at_iso}",
        f"Duration: {duration_s}s",
        f"Git SHA: {report.git_sha}",
        f"Hostname: {report.hostname}",
        f"Reporter: {report.reporter_process}",
        "",
        "## Summary",
        f"Overall: {report.overall_severity}",
        "",
    ]

    for section in report.sections:
        lines.extend(
            [
                f"## {section.title}",
                "",
                section.summary,
                "",
                "| Signal | Value | Status | Δ |",
                "|--------|-------|--------|---|",
            ]
        )
        for row in section.rows:
            prev = previous_metrics.get(row.key)
            prev_value = prev.value if prev is not None else None
            delta = format_metric_delta(row.value, prev_value)
            lines.append(
                f"| {row.key} | {row.display} | {row.status} | {delta} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_email_subject(report: DailyOpsReportResult) -> str:
    date_part = report.generated_at_iso[:10]
    return f"[{report.overall_severity}] Daily Ops Report — {date_part}"
