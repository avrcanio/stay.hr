"""Unit tests for derived component health (no new counters)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.component_health import (
    build_components_status,
    derive_database_component,
    derive_event_bus_component,
    derive_sse_component,
)


def _bus(**overrides):
    base = {
        "backend": "redis",
        "available": True,
        "publish_count": 0,
        "receive_count": 0,
        "local_fallback_count": 0,
        "dedupe_drop_count": 0,
        "redis_reconnect_count": 0,
    }
    base.update(overrides)
    return base


class EventBusComponentTests(SimpleTestCase):
    def test_healthy_default(self):
        self.assertEqual(
            derive_event_bus_component(_bus()),
            {"status": "healthy", "reason": None},
        )

    def test_unavailable(self):
        self.assertEqual(
            derive_event_bus_component(_bus(available=False)),
            {"status": "critical", "reason": "unavailable"},
        )

    def test_publish_without_receive_only_when_sse_active(self):
        bus = _bus(publish_count=3, receive_count=0)
        self.assertEqual(
            derive_event_bus_component(bus, sse={"active_stream_count": 0}),
            {"status": "healthy", "reason": None},
        )
        self.assertEqual(
            derive_event_bus_component(bus, sse={"active_stream_count": 2}),
            {"status": "critical", "reason": "publish_without_receive"},
        )

    def test_publish_without_receive_skipped_for_in_process(self):
        bus = _bus(backend="in_process", publish_count=5, receive_count=0)
        self.assertEqual(
            derive_event_bus_component(bus, sse={"active_stream_count": 1}),
            {"status": "healthy", "reason": None},
        )

    def test_fallback_used(self):
        self.assertEqual(
            derive_event_bus_component(_bus(local_fallback_count=1)),
            {"status": "warning", "reason": "fallback_used"},
        )

    def test_reconnect_loop_threshold(self):
        self.assertEqual(
            derive_event_bus_component(_bus(redis_reconnect_count=2)),
            {"status": "healthy", "reason": None},
        )
        self.assertEqual(
            derive_event_bus_component(_bus(redis_reconnect_count=3)),
            {"status": "warning", "reason": "reconnect_loop"},
        )

    def test_critical_beats_warning(self):
        self.assertEqual(
            derive_event_bus_component(
                _bus(available=False, local_fallback_count=9, redis_reconnect_count=99)
            ),
            {"status": "critical", "reason": "unavailable"},
        )


class SseComponentTests(SimpleTestCase):
    def test_healthy(self):
        self.assertEqual(
            derive_sse_component({"invariant_delta": 0, "invariant_ok": True}),
            {"status": "healthy", "reason": None},
        )

    def test_invariant_breach(self):
        self.assertEqual(
            derive_sse_component({"invariant_delta": 1, "invariant_ok": False}),
            {"status": "critical", "reason": "invariant_breach"},
        )
        self.assertEqual(
            derive_sse_component({"invariant_delta": -1, "invariant_ok": True}),
            {"status": "critical", "reason": "invariant_breach"},
        )


class DatabaseComponentTests(SimpleTestCase):
    def test_healthy(self):
        self.assertEqual(
            derive_database_component({"ok": True, "latency_ms": 1.2}),
            {"status": "healthy", "reason": None},
        )

    def test_unavailable(self):
        self.assertEqual(
            derive_database_component({"ok": False, "latency_ms": None}),
            {"status": "critical", "reason": "unavailable"},
        )


class BuildComponentsStatusTests(SimpleTestCase):
    def test_all_healthy(self):
        components = build_components_status(
            event_bus=_bus(backend="in_process"),
            sse={"invariant_delta": 0, "invariant_ok": True},
            database={"ok": True, "latency_ms": 0.5},
        )
        self.assertEqual(
            components,
            {
                "event_bus": {"status": "healthy", "reason": None},
                "sse": {"status": "healthy", "reason": None},
                "database": {"status": "healthy", "reason": None},
            },
        )
