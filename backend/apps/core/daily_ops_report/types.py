"""Types for daily ops report collectors and formatting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    OK = "OK"
    WARN = "WARN"
    CRIT = "CRIT"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.OK: 0,
    Severity.WARN: 1,
    Severity.CRIT: 2,
}


def max_severity(*severities: Severity) -> Severity:
    if not severities:
        return Severity.OK
    return max(severities, key=lambda s: SEVERITY_ORDER[s])


@dataclass(frozen=True)
class MetricResult:
    key: str
    value: float | int | str | None
    status: Severity
    display: str


@dataclass
class ReportSection:
    title: str
    severity: Severity
    rows: list[MetricResult]
    summary: str


@dataclass
class DailyOpsReportResult:
    sections: list[ReportSection]
    overall_severity: Severity
    duration_ms: int
    generated_at_iso: str
    reporter_process: str
    git_sha: str
    hostname: str
    metrics: dict[str, MetricResult]
