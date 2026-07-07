from __future__ import annotations

import queue

from django.test import SimpleTestCase

from apps.reservations.reservation_version_events import (
    emit_reservation_version_event,
    format_sse,
    subscribe,
    unsubscribe,
)


class ReservationVersionEventsTests(SimpleTestCase):
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
