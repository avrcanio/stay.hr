"""Reservation version EventBus (ADR 0005 Phase 2a).

Separates **event distribution** from SSE transport:

- ``InProcessEventBus`` — same-process fan-out (default / rollback)
- ``RedisEventBus`` — pub/sub across Gunicorn workers and Celery

Lifecycle instrumentation (registry, invariant, opened/closed) stays in
``reservation_version_events``; Redis replaces fan-out only.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Protocol

from django.conf import settings

from apps.reservations.reservation_version_events import (
    emit_reservation_version_event,
    subscribe as local_subscribe,
    unsubscribe as local_unsubscribe,
)

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "stay:v1:reservation_version:"
CHANNEL_PATTERN = f"{CHANNEL_PREFIX}*"
EVENT_TYPE = "reservation_version_changed"

_bus_lock = threading.Lock()
_bus_instance: ReservationVersionEventBus | None = None


class ReservationVersionEventBus(Protocol):
    def publish(
        self, reservation_id: int, scope: str, version: int, tenant_slug: str
    ) -> None: ...

    def subscribe(self, reservation_id: int, scope: str) -> queue.Queue: ...

    def unsubscribe(
        self, reservation_id: int, scope: str, event_queue: queue.Queue
    ) -> None: ...

    def is_available(self) -> bool:
        """True when bus is connected/ready; no exceptions for degraded state."""
        ...


def redis_channel(tenant_slug: str) -> str:
    slug = (tenant_slug or "unknown").strip() or "unknown"
    return f"{CHANNEL_PREFIX}{slug}"


def detect_producer() -> str:
    """Identify publish origin for envelope ``producer`` (ops/debug)."""
    override = getattr(settings, "RESERVATION_VERSION_EVENT_PRODUCER", None)
    if override:
        return str(override)
    try:
        from celery import current_task

        request = getattr(current_task, "request", None)
        if request is not None and getattr(request, "id", None):
            return "celery"
    except Exception:
        pass
    if any("celery" in arg for arg in sys.argv):
        return "celery"
    if "gunicorn" in sys.modules or os.environ.get("SERVER_SOFTWARE", "").startswith(
        "gunicorn"
    ):
        return "gunicorn"
    return "django"


def build_event_envelope(
    *,
    reservation_id: int,
    scope: str,
    version: int,
    tenant_slug: str,
    producer: str | None = None,
    event_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "type": EVENT_TYPE,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "producer": producer or detect_producer(),
        "tenant_slug": tenant_slug or "unknown",
        "reservation_id": int(reservation_id),
        "scope": str(scope),
        "version": int(version),
    }


def resolve_tenant_slug(reservation_id: int) -> str:
    from apps.reservations.models import Reservation

    slug = (
        Reservation.objects.filter(pk=reservation_id)
        .values_list("tenant__slug", flat=True)
        .first()
    )
    return slug or "unknown"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_bus_metrics() -> dict[str, Any]:
    return {
        "publish_count": 0,
        "receive_count": 0,
        "local_fallback_count": 0,
        "dedupe_drop_count": 0,
        "redis_reconnect_count": 0,
        "last_publish_at": None,
        "last_receive_at": None,
        "last_fallback_at": None,
        "last_dedupe_drop_at": None,
    }


class InProcessEventBus:
    """Wraps in-process fan-out; ``is_available()`` always True."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._publish_count = 0
        self._receive_count = 0
        self._last_publish_at: str | None = None
        self._last_receive_at: str | None = None

    def publish(
        self, reservation_id: int, scope: str, version: int, tenant_slug: str
    ) -> None:
        del tenant_slug  # channel is local; slug unused
        emit_reservation_version_event(reservation_id, scope, version)
        now = _utc_now_iso()
        with self._lock:
            self._publish_count += 1
            self._receive_count += 1
            self._last_publish_at = now
            self._last_receive_at = now

    def subscribe(self, reservation_id: int, scope: str) -> queue.Queue[dict[str, Any]]:
        return local_subscribe(reservation_id, scope)

    def unsubscribe(
        self,
        reservation_id: int,
        scope: str,
        event_queue: queue.Queue[dict[str, Any]],
    ) -> None:
        local_unsubscribe(reservation_id, scope, event_queue)

    def is_available(self) -> bool:
        return True

    def bus_metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "publish_count": self._publish_count,
                "receive_count": self._receive_count,
                "local_fallback_count": 0,
                "dedupe_drop_count": 0,
                "redis_reconnect_count": 0,
                "last_publish_at": self._last_publish_at,
                "last_receive_at": self._last_receive_at,
                "last_fallback_at": None,
                "last_dedupe_drop_at": None,
            }


class RedisEventBus:
    """Redis pub/sub fan-out across processes (Phase 2a).

    Publish goes to ``stay:v1:reservation_version:{tenant_slug}``.
    A daemon subscriber thread psubscribes the pattern and forwards matching
    events into the local listener queues used by SSE.
    """

    _SEEN_EVENT_ID_LIMIT = 2048

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or getattr(
            settings, "REDIS_URL", "redis://localhost:6379/0"
        )
        self._lock = threading.Lock()
        self._connected = False
        self._reconnect_count = 0
        self._publish_count = 0
        self._receive_count = 0
        self._local_fallback_count = 0
        self._dedupe_drop_count = 0
        self._last_publish_at: str | None = None
        self._last_receive_at: str | None = None
        self._last_fallback_at: str | None = None
        self._last_dedupe_drop_at: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._client = None
        self._seen_event_ids: OrderedDict[str, None] = OrderedDict()
        self._last_versions: dict[tuple[int, str], int] = {}

    def is_available(self) -> bool:
        with self._lock:
            if self._connected:
                return True
        try:
            self._get_publish_client().ping()
        except Exception:
            return False
        with self._lock:
            self._connected = True
        return True

    def bus_metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "publish_count": self._publish_count,
                "receive_count": self._receive_count,
                "local_fallback_count": self._local_fallback_count,
                "dedupe_drop_count": self._dedupe_drop_count,
                "redis_reconnect_count": self._reconnect_count,
                "last_publish_at": self._last_publish_at,
                "last_receive_at": self._last_receive_at,
                "last_fallback_at": self._last_fallback_at,
                "last_dedupe_drop_at": self._last_dedupe_drop_at,
            }

    def subscribe(self, reservation_id: int, scope: str) -> queue.Queue[dict[str, Any]]:
        self.ensure_subscriber_started()
        return local_subscribe(reservation_id, scope)

    def unsubscribe(
        self,
        reservation_id: int,
        scope: str,
        event_queue: queue.Queue[dict[str, Any]],
    ) -> None:
        local_unsubscribe(reservation_id, scope, event_queue)

    def publish(
        self, reservation_id: int, scope: str, version: int, tenant_slug: str
    ) -> None:
        slug = (tenant_slug or "").strip() or resolve_tenant_slug(reservation_id)
        envelope = build_event_envelope(
            reservation_id=reservation_id,
            scope=scope,
            version=version,
            tenant_slug=slug,
        )
        channel = redis_channel(slug)
        try:
            client = self._get_publish_client()
            client.publish(channel, json.dumps(envelope, separators=(",", ":")))
            now = _utc_now_iso()
            with self._lock:
                self._connected = True
                self._publish_count += 1
                self._last_publish_at = now
        except Exception:
            logger.exception(
                "reservation_version_redis_publish_failed reservation=%s scope=%s "
                "version=%s channel=%s; falling back to in-process fan-out",
                reservation_id,
                scope,
                version,
                channel,
            )
            now = _utc_now_iso()
            with self._lock:
                self._connected = False
                self._local_fallback_count += 1
                self._last_fallback_at = now
            emit_reservation_version_event(reservation_id, scope, version)

    def ensure_subscriber_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._subscriber_loop,
                name="reservation-version-redis-bus",
                daemon=True,
            )
            self._thread.start()

    def stop_subscriber_for_tests(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            self._thread = None
            self._connected = False
            self._client = None
            self._seen_event_ids.clear()
            self._last_versions.clear()
            self._publish_count = 0
            self._receive_count = 0
            self._local_fallback_count = 0
            self._dedupe_drop_count = 0
            self._reconnect_count = 0
            self._last_publish_at = None
            self._last_receive_at = None
            self._last_fallback_at = None
            self._last_dedupe_drop_at = None

    def handle_envelope(self, envelope: dict[str, Any]) -> bool:
        """Validate, dedupe, and fan-out locally. Returns True if delivered."""
        if not isinstance(envelope, dict):
            return False
        if envelope.get("type") != EVENT_TYPE:
            return False
        try:
            reservation_id = int(envelope["reservation_id"])
            scope = str(envelope["scope"])
            version = int(envelope["version"])
        except (KeyError, TypeError, ValueError):
            logger.warning("reservation_version_redis_bad_envelope keys=%s", sorted(envelope))
            return False

        event_id = str(envelope.get("event_id") or "")
        if not self._accept_event(reservation_id, scope, version, event_id):
            now = _utc_now_iso()
            with self._lock:
                self._dedupe_drop_count += 1
                self._last_dedupe_drop_at = now
            return False

        emit_reservation_version_event(reservation_id, scope, version)
        now = _utc_now_iso()
        with self._lock:
            self._receive_count += 1
            self._last_receive_at = now
        return True

    def _accept_event(
        self,
        reservation_id: int,
        scope: str,
        version: int,
        event_id: str,
    ) -> bool:
        with self._lock:
            if event_id:
                if event_id in self._seen_event_ids:
                    return False
                self._seen_event_ids[event_id] = None
                while len(self._seen_event_ids) > self._SEEN_EVENT_ID_LIMIT:
                    self._seen_event_ids.popitem(last=False)

            key = (reservation_id, scope)
            last = self._last_versions.get(key)
            if last is not None and version <= last:
                return False
            self._last_versions[key] = version
            return True

    def _get_publish_client(self):
        import redis

        with self._lock:
            if self._client is None:
                self._client = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                )
            return self._client

    def _subscriber_loop(self) -> None:
        import redis

        backoff = 0.5
        while not self._stop.is_set():
            pubsub = None
            try:
                client = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5.0,
                    socket_timeout=None,
                )
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.psubscribe(CHANNEL_PATTERN)
                with self._lock:
                    self._connected = True
                backoff = 0.5
                logger.info(
                    "reservation_version_redis_bus_subscribed pattern=%s",
                    CHANNEL_PATTERN,
                )
                while not self._stop.is_set():
                    message = pubsub.get_message(timeout=1.0)
                    if message is None:
                        continue
                    if message.get("type") not in {"pmessage", "message"}:
                        continue
                    data = message.get("data")
                    self._dispatch_raw(data)
            except Exception:
                with self._lock:
                    self._connected = False
                    self._reconnect_count += 1
                    reconnect_count = self._reconnect_count
                logger.exception(
                    "reservation_version_redis_bus_disconnected reconnect_count=%s",
                    reconnect_count,
                )
                if self._stop.wait(timeout=backoff):
                    break
                backoff = min(backoff * 2, 30.0)
            finally:
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except Exception:
                        pass

        with self._lock:
            self._connected = False

    def _dispatch_raw(self, data: Any) -> None:
        if data is None:
            return
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        if not isinstance(data, str):
            return
        try:
            envelope = json.loads(data)
        except json.JSONDecodeError:
            logger.warning("reservation_version_redis_invalid_json")
            return
        self.handle_envelope(envelope)


def get_event_bus_backend_name() -> str:
    raw = getattr(settings, "RESERVATION_VERSION_EVENT_BUS", "in_process")
    name = str(raw or "in_process").strip().lower()
    if name not in {"in_process", "redis"}:
        logger.warning(
            "invalid RESERVATION_VERSION_EVENT_BUS=%r; using in_process",
            raw,
        )
        return "in_process"
    return name


def create_reservation_version_event_bus(
    backend: str | None = None,
) -> ReservationVersionEventBus:
    name = (backend or get_event_bus_backend_name()).strip().lower()
    if name == "redis":
        return RedisEventBus()
    return InProcessEventBus()


def get_reservation_version_event_bus() -> ReservationVersionEventBus:
    global _bus_instance
    with _bus_lock:
        if _bus_instance is None:
            _bus_instance = create_reservation_version_event_bus()
        return _bus_instance


def reset_reservation_version_event_bus_for_tests() -> None:
    """Drop singleton (and stop Redis subscriber). Test-only."""
    global _bus_instance
    with _bus_lock:
        bus = _bus_instance
        _bus_instance = None
    if isinstance(bus, RedisEventBus):
        bus.stop_subscriber_for_tests()


def get_event_bus_status() -> dict[str, Any]:
    """Per-worker EventBus snapshot for ``/system/status`` (resets on recycle)."""
    bus = get_reservation_version_event_bus()
    backend = get_event_bus_backend_name()
    metrics = _empty_bus_metrics()
    # Prefer bus_metrics; keep bus_counters alias for older call sites/tests.
    if hasattr(bus, "bus_metrics"):
        metrics.update(bus.bus_metrics())
    elif hasattr(bus, "bus_counters"):
        metrics.update(bus.bus_counters())
    return {
        "backend": backend,
        "available": bool(bus.is_available()),
        **metrics,
    }
