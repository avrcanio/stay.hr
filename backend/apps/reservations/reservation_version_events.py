"""In-process fan-out for reservation version SSE (v2 transport).

Multi-worker deployments need Redis pub/sub later; this module keeps
``publish_reservation_version_changed`` fast for the common single-worker case.

**Metrics scope:** ``active_connections`` and ``peak_connections`` are **per worker
process** (thread-safe within the process only). After Gunicorn worker recycle or
container restart, counters reset to zero.
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any

_listeners: dict[tuple[int, str], list[queue.Queue[dict[str, Any]]]] = {}
_lock = threading.Lock()
_active_connections = 0
_peak_connections = 0


def _channel_key(reservation_id: int, scope: str) -> tuple[int, str]:
    return reservation_id, scope


def subscribe(reservation_id: int, scope: str) -> queue.Queue[dict[str, Any]]:
    global _active_connections, _peak_connections
    event_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=64)
    key = _channel_key(reservation_id, scope)
    with _lock:
        _listeners.setdefault(key, []).append(event_queue)
        _active_connections += 1
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


def get_sse_connection_stats() -> dict[str, int]:
    with _lock:
        return {
            "active_connections": _active_connections,
            "peak_connections": _peak_connections,
        }


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
