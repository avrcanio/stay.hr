"""Process-level runtime stats for observability endpoints."""

from __future__ import annotations

import os
import time

_STARTED_AT_MONO = time.monotonic()


def worker_uptime_seconds() -> int:
    return int(time.monotonic() - _STARTED_AT_MONO)


def gunicorn_config_from_env() -> dict[str, int | str]:
    return {
        "workers": int(os.environ.get("GUNICORN_WORKERS", "8")),
        "worker_class": os.environ.get("GUNICORN_WORKER_CLASS", "sync"),
    }
