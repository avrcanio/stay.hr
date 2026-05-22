from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.booking_service import (
    IMPORT_SOURCE_SMOOBU,
    process_smoobu_booking,
    smoobu_external_id,
    sync_smoobu_reservations,
)
from apps.properties.models import Property, Unit
from apps.reservations.guest_slots import PLACEHOLDER_NAME
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant


def _sample_booking(**overrides) -> dict:
    base = {
        "id": 9001001,
        "reference-id": "BCOM-REF-9001",
        "type": "reservation",
        "arrival": "2026-06-10",
        "departure": "2026-06-12",
        "created-at": "2026-06-01 10:00",
        "modified-at": "2026-06-01 10:00",
        "apartment": {"id": 3327457, "name": "Uzorita R1"},
        "channel": {"id": 1, "name": "Booking.com"},
        "guest-name": "Ana Anić",
        "email": "ana@example.com",
        "phone": "+385911111111",
        "adults": 2,
        "children": 0,
        "price": 220,
        "is-blocked-booking": False,
    }
    base.update(overrides)
    return base


class SmoobuBookingIngestTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="Room 1",
            capacity_max_guests=4,
            capacity_adults=2,
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            property=self.property,
            provider=IntegrationConfig.Provider.SMOOBU,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "api_base": "https://login.smoobu.com",
                "api_key": "test-key",
                "apartments": [
                    {
                        "unit_code": "R1",
                        "smoobu_apartment_id": 3327457,
                        "unit_id": self.unit.id,
                    }
                ],
            }
        )
        self.integration.save()

    @patch("apps.core.tasks.notify_new_reservation.delay")
    def test_creates_reservation_and_guest(self, mock_notify):
        result = process_smoobu_booking(self.integration, _sample_booking())

        self.assertTrue(result.created)
        self.assertFalse(result.skipped)
        reservation = Reservation.objects.get(
            tenant=self.tenant,
            booking_code="BCOM-REF-9001",
            import_source=IMPORT_SOURCE_SMOOBU,
        )
        self.assertEqual(reservation.external_id, "BCOM-REF-9001")
        self.assertEqual(reservation.booking_code, "BCOM-REF-9001")
        self.assertEqual(reservation.booker_name, "Ana Anić")
        self.assertEqual(reservation.check_in, date(2026, 6, 10))
        self.assertEqual(ReservationUnit.objects.filter(reservation=reservation).count(), 1)
        self.assertEqual(Guest.objects.filter(reservation=reservation, is_primary=True).count(), 1)
        mock_notify.assert_called_once_with(reservation.pk)

    @patch("apps.core.tasks.notify_new_reservation.delay")
    def test_creates_placeholder_guest_for_second_adult(self, mock_notify):
        result = process_smoobu_booking(
            self.integration,
            _sample_booking(adults=2, children=0),
        )

        self.assertTrue(result.created)
        reservation = result.reservation
        self.assertEqual(Guest.objects.filter(reservation=reservation).count(), 2)
        self.assertTrue(
            Guest.objects.filter(
                reservation=reservation,
                is_primary=False,
                name=PLACEHOLDER_NAME,
            ).exists()
        )

    def test_updates_existing_reservation(self):
        booking = _sample_booking()
        process_smoobu_booking(self.integration, booking)
        booking["price"] = 250
        booking["modified-at"] = "2026-06-02 12:00"
        result = process_smoobu_booking(self.integration, booking)

        self.assertFalse(result.created)
        self.assertTrue(result.updated)
        reservation = Reservation.objects.get(booking_code="BCOM-REF-9001")
        self.assertEqual(reservation.amount, Decimal("250"))

    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    def test_cancel_triggers_status_notification(self, mock_status_notify):
        process_smoobu_booking(self.integration, _sample_booking())
        result = process_smoobu_booking(
            self.integration,
            _sample_booking(
                **{
                    "type": "cancellation",
                    "modified-at": "2026-06-03 09:00",
                }
            ),
        )

        reservation = result.reservation
        self.assertEqual(reservation.status, Reservation.Status.CANCELED)
        mock_status_notify.assert_called_once()
        args = mock_status_notify.call_args[0]
        self.assertEqual(args[0], reservation.pk)
        self.assertEqual(args[1], Reservation.Status.EXPECTED)
        self.assertEqual(args[2], Reservation.Status.CANCELED)

    def test_preserves_checked_in_on_channel_update(self):
        booking = _sample_booking()
        process_smoobu_booking(self.integration, booking)
        reservation = Reservation.objects.get(booking_code="BCOM-REF-9001")
        reservation.status = Reservation.Status.CHECKED_IN
        reservation.save(update_fields=["status", "updated_at"])

        process_smoobu_booking(
            self.integration,
            _sample_booking(**{"price": 999, "modified-at": "2026-06-04 08:00"}),
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertEqual(reservation.amount, Decimal("999"))

    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    def test_smoobu_cancels_xls_row_when_newer(self, mock_status_notify):
        xls_at = timezone.now() - timedelta(days=1)
        xls_reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5555555",
            booking_code="BCOM-REF-9001",
            import_source="booking_xls",
            check_in=date(2026, 6, 10),
            check_out=date(2026, 6, 12),
            status=Reservation.Status.EXPECTED,
            booker_name="XLS Guest",
            amount=Decimal("100"),
            xls_imported_at=xls_at,
            imported_at=xls_at,
        )

        result = process_smoobu_booking(
            self.integration,
            _sample_booking(
                id=9001002,
                type="cancellation",
                **{"modified-at": "2026-06-03 09:00"},
            ),
        )

        self.assertFalse(result.skipped)
        self.assertTrue(result.updated)
        xls_reservation.refresh_from_db()
        self.assertEqual(xls_reservation.status, Reservation.Status.CANCELED)
        self.assertEqual(xls_reservation.external_id, "5555555")
        self.assertEqual(xls_reservation.smoobu_booking_id, "9001002")
        self.assertEqual(xls_reservation.import_source, IMPORT_SOURCE_SMOOBU)
        self.assertEqual(Reservation.objects.filter(tenant=self.tenant).count(), 1)
        mock_status_notify.assert_called_once()

    def test_skips_stale_smoobu_when_xls_newer(self):
        xls_at = timezone.now()
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5555555",
            booking_code="BCOM-REF-9001",
            import_source="booking_xls",
            check_in=date(2026, 6, 10),
            check_out=date(2026, 6, 12),
            status=Reservation.Status.EXPECTED,
            booker_name="XLS Guest",
            amount=Decimal("100"),
            xls_imported_at=xls_at,
            imported_at=xls_at,
        )

        result = process_smoobu_booking(
            self.integration,
            _sample_booking(
                id=9001002,
                **{"modified-at": "2026-05-01 10:00"},
            ),
        )

        self.assertTrue(result.skipped)
        self.assertEqual(result.skip_reason, "stale_smoobu")
        reservation = Reservation.objects.get(booking_code="BCOM-REF-9001")
        self.assertEqual(reservation.booker_name, "XLS Guest")
        self.assertEqual(reservation.status, Reservation.Status.EXPECTED)

    def test_unknown_apartment_records_error_in_sync(self):
        with patch(
            "apps.integrations.smoobu.booking_service.SmoobuClient.iter_reservations",
            return_value=[_sample_booking(apartment={"id": 9999999, "name": "Unknown"})],
        ):
            stats = sync_smoobu_reservations(self.integration, modified_from="2026-01-01")

        self.assertEqual(stats["created"], 0)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertIn("apartment_id=9999999", stats["errors"][0]["error"])

    @patch("apps.integrations.smoobu.booking_service.SmoobuClient.iter_reservations")
    def test_sync_creates_and_updates_cursor(self, mock_iter):
        mock_iter.return_value = [
            _sample_booking(**{"id": 9002001, "modified-at": "2026-06-05 11:00"}),
        ]
        stats = sync_smoobu_reservations(self.integration, modified_from="2026-01-01")

        self.assertEqual(stats["created"], 1)
        self.integration.refresh_from_db()
        self.assertEqual(
            self.integration.get_config_dict().get("last_sync_modified_from"),
            "2026-06-05 11:00",
        )
