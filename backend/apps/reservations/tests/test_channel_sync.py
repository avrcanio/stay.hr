from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.test import TestCase
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.channel_sync import (
    IMPORT_SOURCE_BOOKING_PDF,
    IMPORT_SOURCE_BOOKING_XLS,
    IMPORT_SOURCE_SMOOBU,
    incoming_wins,
    is_cancellation_status,
    is_pdf_authoritative,
)
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class ChannelSyncTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
        )

    def _reservation(self, **kwargs) -> Reservation:
        defaults = {
            "tenant": self.tenant,
            "property": self.property,
            "external_id": "123",
            "booking_code": "123",
            "check_in": date(2026, 6, 1),
            "check_out": date(2026, 6, 2),
            "booker_name": "Guest",
        }
        defaults.update(kwargs)
        return Reservation.objects.create(**defaults)

    def test_incoming_wins_when_opponent_missing(self):
        reservation = self._reservation()
        now = timezone.now()
        self.assertTrue(
            incoming_wins(reservation, source=IMPORT_SOURCE_SMOOBU, incoming_at=now)
        )
        self.assertTrue(
            incoming_wins(reservation, source=IMPORT_SOURCE_BOOKING_XLS, incoming_at=now)
        )

    def test_smoobu_wins_when_newer_than_xls(self):
        older = timezone.now() - timedelta(hours=2)
        newer = timezone.now()
        reservation = self._reservation(xls_imported_at=older)
        self.assertTrue(
            incoming_wins(reservation, source=IMPORT_SOURCE_SMOOBU, incoming_at=newer)
        )

    def test_smoobu_loses_when_older_than_xls(self):
        older = timezone.now() - timedelta(hours=2)
        newer = timezone.now()
        reservation = self._reservation(xls_imported_at=newer)
        self.assertFalse(
            incoming_wins(reservation, source=IMPORT_SOURCE_SMOOBU, incoming_at=older)
        )

    def test_equal_timestamp_incoming_wins(self):
        ts = timezone.make_aware(datetime(2026, 6, 1, 12, 0), dt_timezone.utc)
        reservation = self._reservation(xls_imported_at=ts)
        self.assertTrue(
            incoming_wins(reservation, source=IMPORT_SOURCE_SMOOBU, incoming_at=ts)
        )

    def test_pdf_authoritative_blocks_smoobu_update(self):
        pdf_at = timezone.now()
        reservation = self._reservation(
            pdf_imported_at=pdf_at,
            import_source=IMPORT_SOURCE_BOOKING_PDF,
        )
        self.assertTrue(is_pdf_authoritative(reservation))
        self.assertFalse(
            incoming_wins(
                reservation,
                source=IMPORT_SOURCE_SMOOBU,
                incoming_at=timezone.now() + timedelta(days=1),
                incoming_status=Reservation.Status.EXPECTED,
            )
        )

    def test_pdf_authoritative_allows_smoobu_cancellation(self):
        pdf_at = timezone.now()
        reservation = self._reservation(
            pdf_imported_at=pdf_at,
            import_source=IMPORT_SOURCE_BOOKING_PDF,
        )
        self.assertTrue(
            incoming_wins(
                reservation,
                source=IMPORT_SOURCE_SMOOBU,
                incoming_at=timezone.now() + timedelta(days=1),
                incoming_status=Reservation.Status.CANCELED,
            )
        )
        self.assertTrue(is_cancellation_status(Reservation.Status.CANCELED))

    def test_pdf_reimport_uses_timestamp_logic(self):
        pdf_at = timezone.now() - timedelta(hours=1)
        reservation = self._reservation(
            pdf_imported_at=pdf_at,
            import_source=IMPORT_SOURCE_BOOKING_PDF,
            smoobu_modified_at=timezone.now(),
        )
        self.assertTrue(
            incoming_wins(
                reservation,
                source=IMPORT_SOURCE_BOOKING_PDF,
                incoming_at=timezone.now(),
            )
        )
