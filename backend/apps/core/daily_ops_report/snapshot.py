"""Snapshot persistence, delta source, and retention."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.core.daily_ops_report.export import SCHEMA_VERSION, export_json, metrics_from_snapshot
from apps.core.daily_ops_report.types import DailyOpsReportResult, MetricResult

ZAGREB = ZoneInfo("Europe/Zagreb")
_REPORT_DIR_REL = Path("ops") / "daily_ops_report"


def report_dir() -> Path:
    path = Path(settings.MEDIA_ROOT) / _REPORT_DIR_REL
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_path() -> Path:
    return report_dir() / "snapshot.json"


def latest_markdown_path() -> Path:
    return report_dir() / "latest.md"


def archive_markdown_path(report_date: str) -> Path:
    return report_dir() / f"{report_date}.md"


def load_snapshot() -> dict | None:
    path = snapshot_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_previous_metrics() -> dict[str, MetricResult]:
    return metrics_from_snapshot(load_snapshot())


def save_snapshot(report: DailyOpsReportResult) -> Path:
    payload = export_json(report)
    path = snapshot_path()
    backup = path.with_suffix(".json.bak")
    if path.is_file():
        path.replace(backup)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_markdown_files(report: DailyOpsReportResult, markdown: str) -> tuple[Path, Path]:
    report_date = report.generated_at_iso[:10]
    latest = latest_markdown_path()
    archive = archive_markdown_path(report_date)
    latest.write_text(markdown, encoding="utf-8")
    archive.write_text(markdown, encoding="utf-8")
    return latest, archive


def prune_old_files(*, keep_days: int | None = None) -> int:
    keep_days = keep_days if keep_days is not None else int(
        getattr(settings, "DAILY_OPS_REPORT_KEEP_DAYS", 90)
    )
    if keep_days <= 0:
        return 0

    cutoff = datetime.now(ZAGREB).date() - timedelta(days=keep_days)
    removed = 0
    directory = report_dir()

    for path in directory.glob("????-??-??.md"):
        try:
            file_date = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            path.unlink(missing_ok=True)
            removed += 1

    for path in directory.glob("snapshot.json.bak"):
        try:
            mtime_date = datetime.fromtimestamp(path.stat().st_mtime, tz=ZAGREB).date()
        except OSError:
            continue
        if mtime_date < cutoff:
            path.unlink(missing_ok=True)
            removed += 1

    return removed
