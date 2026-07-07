import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase

from apps.properties.models import Property
from apps.reservations.models import Reservation, ReservationVersion, ReservationVersionScope
from apps.reservations.reservation_version import (
    publish_reservation_version_changed,
    touch_reservation_version,
)
from apps.tenants.models import Tenant

_TOUCH_LATENCY_SAMPLES = 50
_TOUCH_LATENCY_P95_MS = 5.0
_TOUCH_LATENCY_MEDIAN_MS = 5.0


class ReservationVersionTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Version Tenant", slug="version-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Version Property",
            slug="version-property",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-VERSION",
            check_in="2026-07-01",
            check_out="2026-07-05",
            status=Reservation.Status.EXPECTED,
            booker_name="Test Guest",
            amount=Decimal("100.00"),
        )

    def test_touch_creates_row_and_increments_from_zero(self):
        touch_reservation_version(
            self.reservation.id,
            ReservationVersionScope.MESSAGES,
            reason="test_first_bump",
        )

        row = ReservationVersion.objects.get(
            reservation_id=self.reservation.id,
            scope=ReservationVersionScope.MESSAGES,
        )
        self.assertEqual(row.version, 1)

    def test_touch_increments_existing_version(self):
        touch_reservation_version(self.reservation.id, ReservationVersionScope.MESSAGES)
        touch_reservation_version(
            self.reservation.id,
            ReservationVersionScope.MESSAGES,
            reason="second_bump",
        )

        row = ReservationVersion.objects.get(
            reservation_id=self.reservation.id,
            scope=ReservationVersionScope.MESSAGES,
        )
        self.assertEqual(row.version, 2)

    def test_touch_no_op_when_reservation_id_is_none(self):
        touch_reservation_version(None, ReservationVersionScope.MESSAGES)
        self.assertEqual(ReservationVersion.objects.count(), 0)

    def test_scopes_are_independent(self):
        touch_reservation_version(self.reservation.id, ReservationVersionScope.MESSAGES)
        touch_reservation_version(self.reservation.id, ReservationVersionScope.MESSAGES)
        touch_reservation_version(self.reservation.id, ReservationVersionScope.PAYMENTS)

        messages = ReservationVersion.objects.get(
            reservation_id=self.reservation.id,
            scope=ReservationVersionScope.MESSAGES,
        )
        payments = ReservationVersion.objects.get(
            reservation_id=self.reservation.id,
            scope=ReservationVersionScope.PAYMENTS,
        )
        self.assertEqual(messages.version, 2)
        self.assertEqual(payments.version, 1)

    @patch("apps.reservations.reservation_version.publish_reservation_version_changed")
    def test_touch_calls_publish_with_new_version(self, publish_mock):
        touch_reservation_version(
            self.reservation.id,
            ReservationVersionScope.MESSAGES,
            reason="whatsapp_inbound",
        )

        publish_mock.assert_called_once_with(
            self.reservation.id,
            ReservationVersionScope.MESSAGES,
            1,
        )

    def test_publish_stub_is_no_op(self):
        publish_reservation_version_changed(
            self.reservation.id,
            ReservationVersionScope.MESSAGES,
            1,
        )

    def test_touch_reservation_version_latency(self):
        durations_ms: list[float] = []
        for _ in range(_TOUCH_LATENCY_SAMPLES):
            start = time.perf_counter()
            touch_reservation_version(
                self.reservation.id,
                ReservationVersionScope.MESSAGES,
            )
            durations_ms.append((time.perf_counter() - start) * 1000)

        median_ms = statistics.median(durations_ms)
        p95_ms = statistics.quantiles(durations_ms, n=20)[18]

        self.assertLess(
            median_ms,
            _TOUCH_LATENCY_MEDIAN_MS,
            f"median touch latency {median_ms:.2f}ms exceeds {_TOUCH_LATENCY_MEDIAN_MS}ms",
        )
        self.assertLess(
            p95_ms,
            _TOUCH_LATENCY_P95_MS,
            f"p95 touch latency {p95_ms:.2f}ms exceeds {_TOUCH_LATENCY_P95_MS}ms",
        )


class ReservationVersionConcurrencyTestCase(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrent Tenant", slug="concurrent-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Concurrent Property",
            slug="concurrent-property",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="BK-CONCURRENT",
            check_in="2026-07-01",
            check_out="2026-07-05",
            status=Reservation.Status.EXPECTED,
            booker_name="Concurrent Guest",
            amount=Decimal("100.00"),
        )

    def _touch(self, reason: str) -> None:
        touch_reservation_version(
            self.reservation.id,
            ReservationVersionScope.MESSAGES,
            reason=reason,
        )

    def test_concurrent_touch_increments_exactly(self):
        workers = 8
        touches_per_worker = 5
        expected_version = workers * touches_per_worker

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._touch, f"worker-{i}-{j}")
                for i in range(workers)
                for j in range(touches_per_worker)
            ]
            for future in as_completed(futures):
                future.result()

        row = ReservationVersion.objects.get(
            reservation_id=self.reservation.id,
            scope=ReservationVersionScope.MESSAGES,
        )
        self.assertEqual(row.version, expected_version)

    def test_concurrent_first_bump_race(self):
        workers = 4

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self._touch, f"race-{i}") for i in range(workers)]
            for future in as_completed(futures):
                future.result()

        row = ReservationVersion.objects.get(
            reservation_id=self.reservation.id,
            scope=ReservationVersionScope.MESSAGES,
        )
        self.assertEqual(row.version, workers)
