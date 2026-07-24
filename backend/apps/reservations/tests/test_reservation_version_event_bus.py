from __future__ import annotations

import json
import queue
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.reservations.reservation_version_event_bus import (
    InProcessEventBus,
    RedisEventBus,
    build_event_envelope,
    create_reservation_version_event_bus,
    get_event_bus_status,
    get_reservation_version_event_bus,
    redis_channel,
    reset_reservation_version_event_bus_for_tests,
)
from apps.reservations.reservation_version_events import (
    reset_sse_connection_state_for_tests,
    subscribe as local_subscribe,
    unsubscribe as local_unsubscribe,
)


class ReservationVersionEventBusTests(SimpleTestCase):
    def setUp(self):
        reset_sse_connection_state_for_tests()
        reset_reservation_version_event_bus_for_tests()

    def tearDown(self):
        reset_reservation_version_event_bus_for_tests()
        reset_sse_connection_state_for_tests()

    def test_redis_channel_versioned(self):
        self.assertEqual(
            redis_channel("uzorita"),
            "stay:v1:reservation_version:uzorita",
        )
        self.assertEqual(
            redis_channel(""),
            "stay:v1:reservation_version:unknown",
        )

    def test_envelope_required_fields(self):
        envelope = build_event_envelope(
            reservation_id=130,
            scope="messages",
            version=17,
            tenant_slug="uzorita",
            producer="celery",
            event_id="550e8400-e29b-41d4-a716-446655440000",
            timestamp="2026-07-08T11:00:00+02:00",
        )
        self.assertEqual(
            envelope,
            {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "reservation_version_changed",
                "timestamp": "2026-07-08T11:00:00+02:00",
                "producer": "celery",
                "tenant_slug": "uzorita",
                "reservation_id": 130,
                "scope": "messages",
                "version": 17,
            },
        )

    def test_in_process_bus_delivers_to_subscriber(self):
        bus = InProcessEventBus()
        self.assertTrue(bus.is_available())
        event_queue = bus.subscribe(42, "messages")
        try:
            bus.publish(42, "messages", 3, "demo")
            self.assertEqual(
                event_queue.get(timeout=1),
                {"reservation_id": 42, "scope": "messages", "version": 3},
            )
        finally:
            bus.unsubscribe(42, "messages", event_queue)

    @override_settings(RESERVATION_VERSION_EVENT_BUS="in_process")
    def test_factory_defaults_to_in_process(self):
        bus = create_reservation_version_event_bus()
        self.assertIsInstance(bus, InProcessEventBus)
        status = get_event_bus_status()
        self.assertEqual(status["backend"], "in_process")
        self.assertTrue(status["available"])
        self.assertEqual(status["redis_reconnect_count"], 0)
        self.assertEqual(status["publish_count"], 0)
        self.assertEqual(status["receive_count"], 0)
        self.assertEqual(status["local_fallback_count"], 0)
        self.assertEqual(status["dedupe_drop_count"], 0)
        self.assertIsNone(status["last_publish_at"])
        self.assertIsNone(status["last_receive_at"])
        self.assertIsNone(status["last_fallback_at"])
        self.assertIsNone(status["last_dedupe_drop_at"])

    @override_settings(RESERVATION_VERSION_EVENT_BUS="redis")
    def test_factory_selects_redis(self):
        bus = create_reservation_version_event_bus()
        self.assertIsInstance(bus, RedisEventBus)

    def test_redis_handle_envelope_fans_out_locally(self):
        bus = RedisEventBus(redis_url="redis://invalid:6379/0")
        event_queue = local_subscribe(99, "payments")
        try:
            delivered = bus.handle_envelope(
                build_event_envelope(
                    reservation_id=99,
                    scope="payments",
                    version=4,
                    tenant_slug="demo",
                    event_id="evt-1",
                )
            )
            self.assertTrue(delivered)
            self.assertEqual(event_queue.get(timeout=1)["version"], 4)
        finally:
            local_unsubscribe(99, "payments", event_queue)
            bus.stop_subscriber_for_tests()

    def test_redis_dedupes_event_id_and_stale_version(self):
        bus = RedisEventBus(redis_url="redis://invalid:6379/0")
        event_queue = local_subscribe(7, "messages")
        try:
            first = build_event_envelope(
                reservation_id=7,
                scope="messages",
                version=10,
                tenant_slug="demo",
                event_id="same-id",
            )
            self.assertTrue(bus.handle_envelope(first))
            self.assertEqual(event_queue.get(timeout=1)["version"], 10)

            # duplicate event_id
            self.assertFalse(bus.handle_envelope(dict(first)))
            with self.assertRaises(queue.Empty):
                event_queue.get(timeout=0.05)

            # stale / out-of-order version
            stale = build_event_envelope(
                reservation_id=7,
                scope="messages",
                version=9,
                tenant_slug="demo",
                event_id="newer-id",
            )
            self.assertFalse(bus.handle_envelope(stale))
            with self.assertRaises(queue.Empty):
                event_queue.get(timeout=0.05)

            counters = bus.bus_metrics()
            self.assertEqual(counters["receive_count"], 1)
            self.assertEqual(counters["dedupe_drop_count"], 2)
            self.assertTrue(counters["last_receive_at"])
            self.assertTrue(counters["last_dedupe_drop_at"])
            self.assertIsNone(counters["last_fallback_at"])
        finally:
            local_unsubscribe(7, "messages", event_queue)
            bus.stop_subscriber_for_tests()

    def test_redis_publish_uses_channel_and_envelope(self):
        bus = RedisEventBus(redis_url="redis://localhost:6379/0")
        mock_client = MagicMock()
        with patch.object(bus, "_get_publish_client", return_value=mock_client):
            bus.publish(130, "messages", 17, "uzorita")
        mock_client.publish.assert_called_once()
        channel, raw = mock_client.publish.call_args.args
        self.assertEqual(channel, "stay:v1:reservation_version:uzorita")
        payload = json.loads(raw)
        self.assertEqual(payload["type"], "reservation_version_changed")
        self.assertEqual(payload["reservation_id"], 130)
        self.assertEqual(payload["scope"], "messages")
        self.assertEqual(payload["version"], 17)
        self.assertEqual(payload["tenant_slug"], "uzorita")
        self.assertIn("event_id", payload)
        self.assertIn("producer", payload)
        self.assertEqual(bus.bus_metrics()["publish_count"], 1)
        self.assertTrue(bus.bus_metrics()["last_publish_at"])
        bus.stop_subscriber_for_tests()

    def test_redis_publish_falls_back_locally_on_failure(self):
        bus = RedisEventBus(redis_url="redis://invalid:6379/0")
        event_queue = InProcessEventBus().subscribe(5, "checkin")
        try:
            with patch.object(
                bus, "_get_publish_client", side_effect=ConnectionError("down")
            ):
                bus.publish(5, "checkin", 2, "demo")
            self.assertEqual(event_queue.get(timeout=1)["version"], 2)
            self.assertFalse(bus.is_available())
            counters = bus.bus_metrics()
            self.assertEqual(counters["publish_count"], 0)
            self.assertEqual(counters["local_fallback_count"], 1)
            self.assertTrue(counters["last_fallback_at"])
            self.assertIsNone(counters["last_publish_at"])
        finally:
            InProcessEventBus().unsubscribe(5, "checkin", event_queue)
            bus.stop_subscriber_for_tests()

    @override_settings(RESERVATION_VERSION_EVENT_BUS="in_process")
    def test_singleton_reset(self):
        first = get_reservation_version_event_bus()
        second = get_reservation_version_event_bus()
        self.assertIs(first, second)
        reset_reservation_version_event_bus_for_tests()
        third = get_reservation_version_event_bus()
        self.assertIsNot(first, third)
