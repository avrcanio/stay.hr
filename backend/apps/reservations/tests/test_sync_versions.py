from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.models import (
    Guest,
    MonthlyStatisticsOverride,
    Reservation,
    ReservationVersion,
    ReservationVersionScope,
)
from apps.reservations.reservation_version import touch_reservation_version
from apps.reservations.sync_versions import (
    RESERVATION_VERSION_SCOPE_ALL,
    build_scoped_versions_payload,
    build_sync_versions_payload,
    fetch_reservation_versions,
    reservation_detail_version,
    reservations_version,
    statistics_version,
    sync_versions_etag,
)
from apps.tenants.models import Tenant


class SyncVersionsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )

    def test_empty_tenant_stable_hashes(self):
        payload = build_sync_versions_payload(self.tenant, 2026)
        self.assertIn("reservations", payload)
        self.assertIn("rooms", payload)
        self.assertEqual(len(payload["reservations"]), 16)
        self.assertIn("2026", payload["statistics"])

    def test_reservation_change_bumps_reservations_version(self):
        before = reservations_version(self.tenant)
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 4, 1),
            check_out=date(2026, 4, 5),
            status=Reservation.Status.EXPECTED,
            booker_name="Test",
            amount=Decimal("100.00"),
        )
        after = reservations_version(self.tenant)
        self.assertNotEqual(before, after)

    def test_override_bumps_statistics_version_for_view_year(self):
        before = statistics_version(self.tenant, 2026)
        MonthlyStatisticsOverride.objects.create(
            tenant=self.tenant,
            year=2025,
            month=4,
            revenue=Decimal("5000.00"),
            nights=40,
        )
        after = statistics_version(self.tenant, 2026)
        self.assertNotEqual(before, after)

    def _create_reservation(self, *, booker_name: str = "Test") -> Reservation:
        return Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 4, 1),
            check_out=date(2026, 4, 5),
            status=Reservation.Status.EXPECTED,
            booker_name=booker_name,
            amount=Decimal("100.00"),
        )

    def test_reservation_detail_version_changes_on_status_update(self):
        reservation = self._create_reservation()
        before = reservation_detail_version(self.tenant, reservation.pk)
        reservation.status = Reservation.Status.CHECKED_IN
        reservation.save(update_fields=["status", "updated_at"])
        after = reservation_detail_version(self.tenant, reservation.pk)
        self.assertNotEqual(before, after)

    def test_reservation_detail_version_unchanged_when_other_reservation_changes(self):
        reservation_a = self._create_reservation(booker_name="A")
        reservation_b = self._create_reservation(booker_name="B")
        before = reservation_detail_version(self.tenant, reservation_a.pk)
        reservation_b.status = Reservation.Status.CHECKED_IN
        reservation_b.save(update_fields=["status", "updated_at"])
        after = reservation_detail_version(self.tenant, reservation_a.pk)
        self.assertEqual(before, after)

    def test_reservation_detail_version_changes_on_guest_update(self):
        reservation = self._create_reservation()
        guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Ana",
            last_name="Anić",
            name="Ana Anić",
            is_primary=True,
        )
        before = reservation_detail_version(self.tenant, reservation.pk)
        guest.first_name = "Anamarija"
        guest.save(update_fields=["first_name", "updated_at"])
        after = reservation_detail_version(self.tenant, reservation.pk)
        self.assertNotEqual(before, after)

    def test_build_sync_versions_payload_includes_reservation_detail(self):
        reservation = self._create_reservation()
        payload = build_sync_versions_payload(
            self.tenant,
            2026,
            reservation_id=reservation.pk,
        )
        self.assertIn("reservation_detail", payload)
        self.assertEqual(len(payload["reservation_detail"]), 16)

    def test_build_sync_versions_payload_returns_none_for_missing_reservation(self):
        payload = build_sync_versions_payload(
            self.tenant,
            2026,
            reservation_id=999999,
        )
        self.assertIsNone(payload)

    def test_fetch_reservation_versions_single_scope_zero_when_missing(self):
        reservation = self._create_reservation()
        versions = fetch_reservation_versions(
            reservation.pk,
            ReservationVersionScope.MESSAGES,
        )
        self.assertEqual(versions, {"messages": 0})

    def test_fetch_reservation_versions_single_scope_returns_version(self):
        reservation = self._create_reservation()
        touch_reservation_version(
            reservation.pk,
            ReservationVersionScope.MESSAGES,
            reason="test",
        )
        touch_reservation_version(
            reservation.pk,
            ReservationVersionScope.MESSAGES,
            reason="test",
        )
        versions = fetch_reservation_versions(
            reservation.pk,
            ReservationVersionScope.MESSAGES,
        )
        self.assertEqual(versions, {"messages": 2})

    def test_fetch_reservation_versions_all_scopes_only_existing_rows(self):
        reservation = self._create_reservation()
        touch_reservation_version(reservation.pk, ReservationVersionScope.MESSAGES)
        touch_reservation_version(reservation.pk, ReservationVersionScope.PAYMENTS)
        versions = fetch_reservation_versions(
            reservation.pk,
            RESERVATION_VERSION_SCOPE_ALL,
        )
        self.assertEqual(versions, {"messages": 1, "payments": 1})

    def test_fetch_reservation_versions_single_scope_query_count(self):
        reservation = self._create_reservation()
        touch_reservation_version(reservation.pk, ReservationVersionScope.MESSAGES)
        with self.assertNumQueries(1):
            fetch_reservation_versions(
                reservation.pk,
                ReservationVersionScope.MESSAGES,
            )

    def test_build_scoped_versions_payload_missing_reservation(self):
        payload = build_scoped_versions_payload(
            self.tenant,
            999999,
            ReservationVersionScope.MESSAGES,
        )
        self.assertIsNone(payload)

    def test_build_scoped_versions_payload_single_scope(self):
        reservation = self._create_reservation()
        payload = build_scoped_versions_payload(
            self.tenant,
            reservation.pk,
            ReservationVersionScope.MESSAGES,
        )
        self.assertEqual(payload, {"versions": {"messages": 0}})

    def test_build_sync_versions_payload_includes_versions_when_requested(self):
        reservation = self._create_reservation()
        touch_reservation_version(reservation.pk, ReservationVersionScope.MESSAGES)
        payload = build_sync_versions_payload(
            self.tenant,
            2026,
            reservation_id=reservation.pk,
            include_versions=True,
        )
        self.assertIn("versions", payload)
        self.assertEqual(payload["versions"], {"messages": 1})

    def test_sync_versions_etag_304_semantics(self):
        payload_a = {"versions": {"messages": 0}}
        payload_b = {"versions": {"messages": 0}}
        payload_c = {"versions": {"messages": 1}}
        etag_a = sync_versions_etag(payload_a)
        etag_b = sync_versions_etag(payload_b)
        etag_c = sync_versions_etag(payload_c)
        self.assertEqual(etag_a, etag_b)
        self.assertNotEqual(etag_a, etag_c)
        self.assertTrue(etag_a.startswith('W/"'))
        self.assertTrue(etag_a.endswith('"'))

    def test_sync_versions_etag_differs_between_full_and_scoped_payload(self):
        reservation = self._create_reservation()
        full = build_sync_versions_payload(
            self.tenant,
            2026,
            reservation_id=reservation.pk,
            include_versions=True,
        )
        scoped = build_scoped_versions_payload(
            self.tenant,
            reservation.pk,
            ReservationVersionScope.MESSAGES,
        )
        self.assertNotEqual(sync_versions_etag(full), sync_versions_etag(scoped))
