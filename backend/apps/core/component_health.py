"""Derived component health for ``/system/status`` (thin ops layer).

No new counters — status/reason are computed from existing payload fields
(ADR 0005 / Phase 2b prep). Values: ``healthy`` | ``warning`` | ``critical``.
"""

from __future__ import annotations

from typing import Any

ComponentStatus = dict[str, Any]

# Absolute reconnect count on a worker process that signals a reconnect loop
# (single blip after recycle is ignored; counters reset on worker recycle).
_RECONNECT_LOOP_THRESHOLD = 3


def _status(status: str, reason: str | None = None) -> ComponentStatus:
    return {"status": status, "reason": reason}


def derive_event_bus_component(
    event_bus: dict[str, Any],
    *,
    sse: dict[str, Any] | None = None,
) -> ComponentStatus:
    """Derive EventBus health from existing ``event_bus`` (+ optional SSE) fields."""
    if not event_bus.get("available", True):
        return _status("critical", "unavailable")

    publish_count = int(event_bus.get("publish_count") or 0)
    receive_count = int(event_bus.get("receive_count") or 0)
    backend = str(event_bus.get("backend") or "in_process").strip().lower()
    sse = sse or {}
    active_streams = int(
        sse.get("active_stream_count")
        if sse.get("active_stream_count") is not None
        else sse.get("active_connections")
        or 0
    )
    # Only flag publish-without-receive on Redis workers that hold SSE and
    # therefore should be receiving fan-out (REST-only / Celery publishers skip).
    if (
        backend == "redis"
        and active_streams > 0
        and publish_count > 0
        and receive_count == 0
    ):
        return _status("critical", "publish_without_receive")

    if int(event_bus.get("local_fallback_count") or 0) > 0:
        return _status("warning", "fallback_used")

    if int(event_bus.get("redis_reconnect_count") or 0) >= _RECONNECT_LOOP_THRESHOLD:
        return _status("warning", "reconnect_loop")

    return _status("healthy")


def derive_sse_component(sse: dict[str, Any]) -> ComponentStatus:
    """Derive SSE health from registry invariant fields."""
    delta = int(sse.get("invariant_delta") or 0)
    invariant_ok = bool(sse.get("invariant_ok", delta == 0))
    if not invariant_ok or delta != 0:
        return _status("critical", "invariant_breach")
    return _status("healthy")


def derive_database_component(database: dict[str, Any]) -> ComponentStatus:
    """Derive DB health from a thin connectivity probe snapshot."""
    if not database.get("ok", False):
        return _status("critical", "unavailable")
    return _status("healthy")


def build_components_status(
    *,
    event_bus: dict[str, Any],
    sse: dict[str, Any],
    database: dict[str, Any],
) -> dict[str, ComponentStatus]:
    return {
        "event_bus": derive_event_bus_component(event_bus, sse=sse),
        "sse": derive_sse_component(sse),
        "database": derive_database_component(database),
    }
