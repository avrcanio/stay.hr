"""Persistent JSON snapshot for document intake quality email reports."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.reservations.document_intake_telemetry import PIPELINE_VERSION, QUALITY_MODEL_ID

SNAPSHOT_SCHEMA_VERSION = 1
ZAGREB = ZoneInfo("Europe/Zagreb")


def report_snapshot_path() -> Path:
    override = (getattr(settings, "DOCUMENT_INTAKE_REPORT_SNAPSHOT_PATH", None) or "").strip()
    if override:
        return Path(override)
    media_root = getattr(settings, "MEDIA_ROOT", None) or ""
    return Path(media_root) / "ops" / "document_intake_report_snapshot.json"


def load_report_snapshot() -> dict | None:
    path = report_snapshot_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_report_snapshot(
    *,
    kpis: dict,
    lookback_days: int,
    send_every_days: int,
    generated_at: datetime | None = None,
) -> None:
    when = generated_at or timezone.now()
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": when.isoformat(),
        "lookback_days": lookback_days,
        "send_every_days": send_every_days,
        "quality_model": QUALITY_MODEL_ID,
        "pipeline_version": PIPELINE_VERSION,
        "kpis": kpis,
        "top_reasons": kpis.get("top_reasons") or [],
    }
    path = report_snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".snapshot-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _snapshot_generated_date(snapshot: dict, *, today: date) -> date | None:
    raw = snapshot.get("generated_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(ZAGREB).date()


def should_send_report_today(
    *,
    snapshot: dict | None,
    send_every_days: int,
    monday_only: bool,
    today: date | None = None,
) -> tuple[bool, str]:
    send_every_days = max(1, int(send_every_days))
    ref = today or timezone.now().astimezone(ZAGREB).date()

    if monday_only and ref.weekday() != 0:
        return False, "monday_only"

    if snapshot is None:
        return True, "no_previous_snapshot"

    last_sent = _snapshot_generated_date(snapshot, today=ref)
    if last_sent is None:
        return True, "invalid_previous_timestamp"

    days_since = (ref - last_sent).days
    if days_since < send_every_days:
        return False, f"interval_not_elapsed({days_since}<{send_every_days})"

    return True, "interval_elapsed"
