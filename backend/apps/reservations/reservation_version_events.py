"""In-process fan-out helpers for reservation version SSE (v2 transport).

Local listener queues and SSE lifecycle metrics live here. Cross-process
distribution is selected via ``ReservationVersionEventBus``
(``reservation_version_event_bus.py``) — ``in_process`` (default) or ``redis``.

**Metrics scope:** all counters in this module are **per worker process**
(thread-safe within the process only). After Gunicorn worker recycle or
container restart, counters reset to zero. Do not treat ``active_connections``
from a single ``/system/status/`` response as a global cluster total — poll
multiple times or aggregate logs for cross-worker visibility.

**Lifecycle invariant:** ``opened_total - closed_total == active_connections``
(and equals ``len(_streams)`` / ``active_stream_count``). Closed streams are
removed from the registry; ``invariant_delta != 0`` means leak/drift — see
``sse_invariant_breach`` logs.

**Permanent instrumentation (ADR 0005):** registry, invariant checks, and
``get_sse_connection_stats()`` fields must remain through Phase 2a (Redis
EventBus) and 2b (Uvicorn SSE). Redis replaces fan-out, not disconnect proof.
Do not remove ``register_sse_stream`` / ``close_sse_stream`` /
``check_sse_invariant`` / ``active_streams`` / ``invariant_delta`` when
introducing a bus or transport split.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_listeners: dict[tuple[int, str], list[queue.Queue[dict[str, Any]]]] = {}
_lock = threading.Lock()
_active_connections = 0
_peak_connections = 0
_connections_opened_total = 0
_connections_closed_total = 0
_duration_sum_seconds = 0.0
_duration_count = 0

# Per-stream registry keyed by stream_id (same id as X-SSE-Stream-Id / connected event).
_streams: dict[str, dict[str, Any]] = {}


def _channel_key(reservation_id: int, scope: str) -> tuple[int, str]:
    return reservation_id, scope


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registry_active_count_locked() -> int:
    return sum(1 for entry in _streams.values() if entry.get("closed_at") is None)


def _invariant_delta_locked() -> int:
    return _connections_opened_total - _connections_closed_total - _active_connections


def subscribe(reservation_id: int, scope: str) -> queue.Queue[dict[str, Any]]:
    global _active_connections, _peak_connections, _connections_opened_total
    event_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=64)
    key = _channel_key(reservation_id, scope)
    with _lock:
        _listeners.setdefault(key, []).append(event_queue)
        _active_connections += 1
        _connections_opened_total += 1
        if _active_connections > _peak_connections:
            _peak_connections = _active_connections
    return event_queue


def unsubscribe(
    reservation_id: int,
    scope: str,
    event_queue: queue.Queue[dict[str, Any]],
) -> None:
    global _active_connections
    key = _channel_key(reservation_id, scope)
    with _lock:
        listeners = _listeners.get(key)
        if not listeners:
            return
        try:
            listeners.remove(event_queue)
        except ValueError:
            return
        if not listeners:
            _listeners.pop(key, None)
        _active_connections = max(0, _active_connections - 1)


def register_sse_stream(
    stream_id: str,
    *,
    reservation_id: int,
    scope: str,
    worker_pid: int | None = None,
    opened_at: str | None = None,
) -> None:
    """Record a live SSE stream in the per-worker registry (keyed by stream_id)."""
    if not stream_id:
        raise ValueError("stream_id is required")
    now = opened_at or _utc_now_iso()
    pid = os.getpid() if worker_pid is None else worker_pid
    with _lock:
        _streams[stream_id] = {
            "stream_id": stream_id,
            "worker_pid": pid,
            "reservation_id": reservation_id,
            "scope": scope,
            "opened_at": now,
            "last_heartbeat": now,
            "closed_at": None,
            "close_reason": None,
        }


def touch_sse_stream(stream_id: str) -> None:
    """Update last_heartbeat after a successful heartbeat or event write."""
    if not stream_id:
        return
    now = _utc_now_iso()
    with _lock:
        entry = _streams.get(stream_id)
        if entry is None or entry.get("closed_at") is not None:
            return
        entry["last_heartbeat"] = now


def close_sse_stream(stream_id: str, reason: str) -> dict[str, Any] | None:
    """Remove stream from the active registry. Returns a closed snapshot or None."""
    if not stream_id:
        return None
    now = _utc_now_iso()
    with _lock:
        entry = _streams.pop(stream_id, None)
        if entry is None:
            return None
        closed = dict(entry)
        closed["closed_at"] = now
        closed["close_reason"] = reason or "unknown"
        return closed


def list_active_sse_streams() -> list[dict[str, Any]]:
    """Return copies of registry entries that are still open."""
    with _lock:
        return [
            dict(entry)
            for entry in _streams.values()
            if entry.get("closed_at") is None
        ]


def check_sse_invariant() -> bool:
    """Log ``sse_invariant_breach`` when opened − closed ≠ active (or registry drift).

    Call after a complete open (subscribe + register) or close
    (record + unsubscribe + close_sse_stream) so counters and registry agree.
    """
    with _lock:
        delta = _invariant_delta_locked()
        registry_active = _registry_active_count_locked()
        ok = delta == 0 and registry_active == _active_connections
        if not ok:
            logger.warning(
                "sse_invariant_breach opened=%s closed=%s active=%s "
                "registry_active=%s invariant_delta=%s",
                _connections_opened_total,
                _connections_closed_total,
                _active_connections,
                registry_active,
                delta,
            )
        return ok


def record_sse_stream_closed(duration_seconds: float) -> None:
    """Record lifetime of a closed SSE stream (closed connections only)."""
    if duration_seconds < 0:
        duration_seconds = 0.0
    global _connections_closed_total, _duration_sum_seconds, _duration_count
    with _lock:
        _connections_closed_total += 1
        _duration_sum_seconds += duration_seconds
        _duration_count += 1


def get_sse_connection_stats() -> dict[str, Any]:
    with _lock:
        average_duration: float | None
        if _duration_count:
            average_duration = round(_duration_sum_seconds / _duration_count, 2)
        else:
            average_duration = None
        registry_active = _registry_active_count_locked()
        delta = _invariant_delta_locked()
        invariant_ok = delta == 0 and registry_active == _active_connections
        active_streams = [
            {
                "stream_id": entry["stream_id"],
                "reservation_id": entry["reservation_id"],
                "scope": entry["scope"],
                "worker_pid": entry["worker_pid"],
                "opened_at": entry["opened_at"],
                "last_heartbeat": entry["last_heartbeat"],
            }
            for entry in _streams.values()
            if entry.get("closed_at") is None
        ]
        return {
            "active_connections": _active_connections,
            "peak_connections": _peak_connections,
            "connections_opened_total": _connections_opened_total,
            "connections_closed_total": _connections_closed_total,
            "closed_streams_sample_count": _duration_count,
            "average_duration_seconds": average_duration,
            "active_stream_count": registry_active,
            "active_streams": active_streams,
            "invariant_ok": invariant_ok,
            "invariant_delta": delta,
        }


def reset_sse_connection_state_for_tests() -> None:
    """Clear in-process SSE listeners, registry, and counters. Test-only."""
    global _active_connections, _peak_connections
    global _connections_opened_total, _connections_closed_total
    global _duration_sum_seconds, _duration_count
    with _lock:
        _listeners.clear()
        _streams.clear()
        _active_connections = 0
        _peak_connections = 0
        _connections_opened_total = 0
        _connections_closed_total = 0
        _duration_sum_seconds = 0.0
        _duration_count = 0


def emit_reservation_version_event(
    reservation_id: int,
    scope: str,
    version: int,
) -> None:
    payload = {
        "reservation_id": reservation_id,
        "scope": scope,
        "version": version,
    }
    key = _channel_key(reservation_id, scope)
    with _lock:
        listeners = list(_listeners.get(key, ()))

    for event_queue in listeners:
        try:
            event_queue.put_nowait(payload)
        except queue.Full:
            # Drop if client is slow; next poll or reconnect will catch up.
            pass


def format_sse(event: str, data: dict[str, Any]) -> str:
    body = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return f"event: {event}\ndata: {body}\n\n"
