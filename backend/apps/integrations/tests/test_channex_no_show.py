from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations.channex.booking_service import channex_external_id
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class ChannexNoShowReportingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R2",
            name="R2",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "property_id": "prop-id",
                "sync_property_slug": "uzorita",
            }
        )
        self.integration.save()
        self.booking_id = "channex-booking-789"
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id=channex_external_id(self.booking_id),
            import_source="channex",
            check_in=date(2026, 5, 27),
            check_out=date(2026, 5, 28),
            status=Reservation.Status.EXPECTED,
            booker_name="Booking Guest",
            amount=Decimal("150.00"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="R2",
            sort_order=0,
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    @patch("apps.integrations.channex.no_show_service.ChannexClient")
    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    def test_channex_no_show_calls_api_with_waived_fees(
        self,
        mock_notify_status,
        mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.report_no_show.return_value = {"meta": {"message": "Success"}}

        response = self.client.patch(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            {"status": Reservation.Status.NO_SHOW, "waived_fees": True},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        mock_client.report_no_show.assert_called_once_with(
            self.booking_id,
            waived_fees=True,
        )
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.NO_SHOW)
        mock_notify_status.assert_called_once()

    @patch("apps.integrations.channex.no_show_service.ChannexClient")
    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    def test_channex_no_show_can_charge_fee(
        self,
        mock_notify_status,
        mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.report_no_show.return_value = {"meta": {"message": "Success"}}

        response = self.client.patch(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            {"status": Reservation.Status.NO_SHOW, "waived_fees": False},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        mock_client.report_no_show.assert_called_once_with(
            self.booking_id,
            waived_fees=False,
        )
        mock_notify_status.assert_called_once()

    @patch("apps.integrations.channex.no_show_service.ChannexClient")
    def test_channex_api_failure_does_not_update_status(self, mock_client_cls):
        from apps.integrations.channex.exceptions import ChannexApiError

        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.report_no_show.side_effect = ChannexApiError("Channex POST failed (422)")

        response = self.client.patch(
            f"/api/v1/reception/reservations/{self.reservation.id}/",
            {"status": Reservation.Status.NO_SHOW, "waived_fees": True},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.EXPECTED)

    @patch("apps.integrations.channex.no_show_service.report_no_show_for_reservation")
    @patch("apps.core.tasks.notify_reservation_status_changed.delay")
    def test_manual_reservation_skips_channex_report(
        self,
        mock_notify_status,
        mock_report,
    ):
        manual = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            import_source="manual",
            check_in=date(2026, 5, 27),
            check_out=date(2026, 5, 28),
            status=Reservation.Status.EXPECTED,
            booker_name="Manual Guest",
        )

        response = self.client.patch(
            f"/api/v1/reception/reservations/{manual.id}/",
            {"status": Reservation.Status.NO_SHOW, "waived_fees": True},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        mock_report.assert_not_called()
        manual.refresh_from_db()
        self.assertEqual(manual.status, Reservation.Status.NO_SHOW)
        mock_notify_status.assert_called_once()
