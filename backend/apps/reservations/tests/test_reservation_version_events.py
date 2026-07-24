from __future__ import annotations

import queue
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.reservations.reservation_version_events import (
    check_sse_invariant,
    close_sse_stream,
    emit_reservation_version_event,
    format_sse,
    get_sse_connection_stats,
    list_active_sse_streams,
    record_sse_stream_closed,
    register_sse_stream,
    reset_sse_connection_state_for_tests,
    subscribe,
    touch_sse_stream,
    unsubscribe,
)


class ReservationVersionEventsTests(SimpleTestCase):
    def setUp(self):
        reset_sse_connection_state_for_tests()

    def tearDown(self):
        reset_sse_connection_state_for_tests()

    def test_emit_delivers_to_subscriber(self):
        event_queue = subscribe(973, "messages")
        try:
            emit_reservation_version_event(973, "messages", 5)
            payload = event_queue.get(timeout=1)
            self.assertEqual(
                payload,
                {"reservation_id": 973, "scope": "messages", "version": 5},
            )
        finally:
            unsubscribe(973, "messages", event_queue)

    def test_unsubscribe_stops_delivery(self):
        event_queue = subscribe(973, "messages")
        unsubscribe(973, "messages", event_queue)
        emit_reservation_version_event(973, "messages", 6)
        with self.assertRaises(queue.Empty):
            event_queue.get(timeout=0.05)

    def test_format_sse(self):
        rendered = format_sse(
            "reservation_version_changed",
            {"reservation_id": 1, "scope": "messages", "version": 2},
        )
        self.assertTrue(rendered.startswith("event: reservation_version_changed\n"))
        self.assertIn('"version":2', rendered)
        self.assertTrue(rendered.endswith("\n\n"))

    def test_sse_connection_stats_average_only_for_closed_streams(self):
        stats = get_sse_connection_stats()
        self.assertIsNone(stats["average_duration_seconds"])
        record_sse_stream_closed(12.5)
        stats = get_sse_connection_stats()
        self.assertEqual(stats["average_duration_seconds"], 12.5)
        self.assertEqual(stats["connections_closed_total"], 1)
        self.assertEqual(stats["closed_streams_sample_count"], 1)

    def test_stream_registry_open_touch_close(self):
        event_queue = subscribe(42, "checkin")
        register_sse_stream(
            "abc123",
            reservation_id=42,
            scope="checkin",
            worker_pid=9,
            opened_at="2026-07-23T12:00:00+00:00",
        )
        self.assertTrue(check_sse_invariant())
        active = list_active_sse_streams()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["stream_id"], "abc123")
        self.assertEqual(active[0]["reservation_id"], 42)
        self.assertEqual(active[0]["scope"], "checkin")
        self.assertIsNone(active[0]["closed_at"])

        touch_sse_stream("abc123")
        after_touch = list_active_sse_streams()[0]
        self.assertGreaterEqual(
            after_touch["last_heartbeat"],
            "2026-07-23T12:00:00+00:00",
        )

        record_sse_stream_closed(1.5)
        unsubscribe(42, "checkin", event_queue)
        closed = close_sse_stream("abc123", "client_disconnect")
        self.assertIsNotNone(closed)
        self.assertEqual(closed["close_reason"], "client_disconnect")
        self.assertTrue(closed["closed_at"])
        self.assertEqual(list_active_sse_streams(), [])
        self.assertTrue(check_sse_invariant())

        stats = get_sse_connection_stats()
        self.assertEqual(stats["active_connections"], 0)
        self.assertEqual(stats["active_stream_count"], 0)
        self.assertEqual(stats["invariant_delta"], 0)
        self.assertTrue(stats["invariant_ok"])
        self.assertEqual(stats["connections_opened_total"], 1)
        self.assertEqual(stats["connections_closed_total"], 1)

    def test_invariant_delta_detects_drift(self):
        event_queue = subscribe(7, "messages")
        register_sse_stream("drift1", reservation_id=7, scope="messages")
        # Simulate forgotten unsubscribe: close registry + record only.
        record_sse_stream_closed(0.1)
        close_sse_stream("drift1", "client_disconnect")
        stats = get_sse_connection_stats()
        self.assertEqual(stats["invariant_delta"], -1)
        self.assertFalse(stats["invariant_ok"])
        with self.assertLogs(
            "apps.reservations.reservation_version_events",
            level="WARNING",
        ) as logs:
            self.assertFalse(check_sse_invariant())
        self.assertTrue(any("sse_invariant_breach" in line for line in logs.output))
        unsubscribe(7, "messages", event_queue)
        self.assertTrue(check_sse_invariant())

    def test_close_sse_stream_idempotent(self):
        event_queue = subscribe(1, "messages")
        try:
            register_sse_stream("once", reservation_id=1, scope="messages")
            first = close_sse_stream("once", "client_disconnect")
            second = close_sse_stream("once", "exception")
            self.assertIsNotNone(first)
            self.assertEqual(first["close_reason"], "client_disconnect")
            self.assertIsNone(second)
        finally:
            record_sse_stream_closed(0.0)
            unsubscribe(1, "messages", event_queue)

    def test_check_sse_invariant_logs_on_registry_mismatch(self):
        event_queue = subscribe(3, "payments")
        try:
            # subscribe without register → registry behind counters
            with patch(
                "apps.reservations.reservation_version_events.logger"
            ) as mock_logger:
                ok = check_sse_invariant()
            self.assertFalse(ok)
            mock_logger.warning.assert_called()
            self.assertIn("sse_invariant_breach", mock_logger.warning.call_args[0][0])
        finally:
            unsubscribe(3, "payments", event_queue)
            record_sse_stream_closed(0.0)
