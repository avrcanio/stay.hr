from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.models import EvisitorGuestStatus, Guest, Reservation
from apps.reservations.tasks import run_auto_checkouts, tenant_local_now
from apps.tenants.models import Tenant, TenantReceptionSettings

ZAGREB = ZoneInfo("Europe/Zagreb")


class AutoCheckoutTaskTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Uzorita",
            slug="uzorita",
            timezone="Europe/Zagreb",
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.settings = TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            auto_checkout_enabled=True,
            auto_checkout_time=time(10, 0),
        )
        self.today = date(2026, 5, 21)
        self.run_at = datetime(2026, 5, 21, 10, 30, tzinfo=ZAGREB)

    def _create_reservation(
        self,
        *,
        check_out: date | None = None,
        status: str = Reservation.Status.CHECKED_IN,
        booking_code: str = "BK-AUTO",
        with_guest: bool = True,
        guest_evisitor_status: str = EvisitorGuestStatus.SENT,
    ) -> Reservation:
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code=booking_code,
            check_in=self.today - timedelta(days=2),
            check_out=check_out or self.today,
            status=status,
            booker_name="Auto Guest",
            amount=Decimal("100.00"),
        )
        if with_guest:
            Guest.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                first_name="Ana",
                last_name="Anić",
                is_primary=True,
                evisitor_status=guest_evisitor_status,
            )
        return reservation

    def _run_task(self, when: datetime | None = None):
        fixed = when or self.run_at
        with patch(
            "apps.reservations.tasks.tenant_local_now",
            side_effect=lambda tenant: fixed,
        ):
            return run_auto_checkouts()

    @patch("apps.core.tasks.notify_auto_checkout_summary.delay")
    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    @patch("apps.reservations.checkout.checkout_reservation_guests_in_evisitor")
    def test_checkout_complete_reservation(
        self,
        mock_evisitor_checkout,
        mock_status_push,
        mock_summary_push,
    ):
        reservation = self._create_reservation()
        mock_evisitor_checkout.return_value = []

        result = self._run_task()

        reservation.refresh_from_db()
        self.settings.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_OUT)
        self.assertEqual(self.settings.auto_checkout_last_run_date, self.today)
        self.assertEqual(result["checked_out"], 1)
        mock_evisitor_checkout.assert_called_once()
        mock_status_push.assert_called_once_with(
            reservation.pk,
            Reservation.Status.CHECKED_IN,
            Reservation.Status.CHECKED_OUT,
        )
        mock_summary_push.assert_not_called()

    def test_disabled_tenant_no_changes(self):
        self.settings.auto_checkout_enabled = False
        self.settings.save(update_fields=["auto_checkout_enabled"])
        reservation = self._create_reservation()

        result = self._run_task()

        reservation.refresh_from_db()
        self.settings.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertIsNone(self.settings.auto_checkout_last_run_date)
        self.assertEqual(result["tenants_processed"], 0)

    def test_before_auto_checkout_time(self):
        reservation = self._create_reservation()
        early = datetime(2026, 5, 21, 9, 45, tzinfo=ZAGREB)

        result = self._run_task(when=early)

        reservation.refresh_from_db()
        self.settings.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertIsNone(self.settings.auto_checkout_last_run_date)
        self.assertEqual(result["tenants_processed"], 0)

    @patch("apps.core.tasks.notify_auto_checkout_summary.delay")
    @patch("apps.reservations.checkout.checkout_reservation_guests_in_evisitor")
    def test_evisitor_incomplete_skipped(
        self,
        mock_evisitor_checkout,
        mock_summary_push,
    ):
        reservation = self._create_reservation(
            guest_evisitor_status=EvisitorGuestStatus.NOT_SENT,
        )

        result = self._run_task()

        reservation.refresh_from_db()
        self.settings.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertEqual(self.settings.auto_checkout_last_run_date, self.today)
        self.assertEqual(result["skipped"], 1)
        mock_evisitor_checkout.assert_not_called()
        mock_summary_push.assert_called_once()
        skipped = mock_summary_push.call_args.args[1]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["reason"], "evisitor_incomplete")

    @patch("apps.core.tasks.notify_auto_checkout_summary.delay")
    @patch("apps.reservations.checkout.checkout_reservation_guests_in_evisitor")
    def test_no_guests_skipped(self, mock_evisitor_checkout, mock_summary_push):
        reservation = self._create_reservation(with_guest=False)

        result = self._run_task()

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertEqual(result["skipped"], 1)
        mock_evisitor_checkout.assert_not_called()
        skipped = mock_summary_push.call_args.args[1]
        self.assertEqual(skipped[0]["reason"], "evisitor_none")

    @patch("apps.reservations.checkout.checkout_reservation_guests_in_evisitor")
    def test_yesterday_check_out_not_included(self, mock_evisitor_checkout):
        reservation = self._create_reservation(
            check_out=self.today - timedelta(days=1),
        )

        result = self._run_task()

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assertEqual(result["checked_out"], 0)
        mock_evisitor_checkout.assert_not_called()

    @patch("apps.core.tasks.notify_auto_checkout_summary.delay")
    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    @patch("apps.reservations.checkout.checkout_reservation_guests_in_evisitor")
    def test_second_run_same_day_is_idempotent(
        self,
        mock_evisitor_checkout,
        mock_status_push,
        mock_summary_push,
    ):
        reservation = self._create_reservation()
        mock_evisitor_checkout.return_value = []

        self._run_task()
        mock_evisitor_checkout.reset_mock()
        mock_status_push.reset_mock()
        mock_summary_push.reset_mock()

        result = self._run_task()

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_OUT)
        self.assertEqual(result["tenants_processed"], 0)
        mock_evisitor_checkout.assert_not_called()
        mock_status_push.assert_not_called()
        mock_summary_push.assert_not_called()

    def test_tenant_local_now_uses_tenant_timezone(self):
        self.tenant.timezone = "Europe/Zagreb"
        self.tenant.save(update_fields=["timezone"])
        now = tenant_local_now(self.tenant)
        self.assertIsNotNone(now.tzinfo)
