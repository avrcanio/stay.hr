"""Shared system status payload for API and daily ops collectors."""

from __future__ import annotations

import os

from apps.core.runtime_stats import (
    SYSTEM_STATUS_SCHEMA_VERSION,
    build_info_from_env,
    gunicorn_config_from_env,
    worker_uptime_seconds,
)
from apps.reservations.reservation_version_events import get_sse_connection_stats


def build_system_status_payload(*, reporter_process: str | None = None) -> dict:
    gunicorn_config = gunicorn_config_from_env()
    payload: dict = {
        "schema_version": SYSTEM_STATUS_SCHEMA_VERSION,
        "metrics_scope": "worker_process",
        "build": build_info_from_env(),
        "gunicorn": {
            **gunicorn_config,
            "pid": os.getpid(),
            "uptime_seconds": worker_uptime_seconds(),
            "timeout": int(os.environ.get("GUNICORN_TIMEOUT", "3600")),
        },
        "sse": get_sse_connection_stats(),
    }
    if reporter_process:
        payload["reporter_process"] = reporter_process
    return payload
