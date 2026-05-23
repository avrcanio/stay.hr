from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations.models import IntegrationConfig, UnitAvailabilityBlock
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class ReceptionUnitBlockAPITests(TestCase):
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
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
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
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_list_blocks_requires_from_to(self):
        response = self.client.get("/api/v1/reception/calendar/blocks/", **self.auth)
        self.assertEqual(response.status_code, 400)

    def test_list_hospira_blocks(self):
        UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            check_in=date(2026, 8, 4),
            check_out=date(2026, 8, 6),
            smoobu_booking_id="99001",
        )
        response = self.client.get(
            "/api/v1/reception/calendar/blocks/?from=2026-08-01&to=2026-08-31",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]["can_unblock"])
        self.assertEqual(data[0]["unit_code"], "R1")
        self.assertIsNone(data[0]["reservation_id"])

    def test_list_hospira_blocks_includes_reservation_id(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 10, 4),
            check_out=date(2026, 10, 5),
            status=Reservation.Status.PENDING,
            booker_name="Ante Vrcan",
        )
        UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reservation=reservation,
            check_in=date(2026, 10, 4),
            check_out=date(2026, 10, 5),
            smoobu_booking_id="140631922",
        )
        response = self.client.get(
            "/api/v1/reception/calendar/blocks/?from=2026-10-01&to=2026-10-31",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["reservation_id"], reservation.id)

    @patch("apps.integrations.smoobu.blocking_service.SmoobuClient")
    def test_create_block(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.create_reservation.return_value = {"id": 12345}

        response = self.client.post(
            f"/api/v1/reception/units/{self.unit.id}/block/",
            {"check_in": "2026-09-01", "check_out": "2026-09-04"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["smoobu_booking_id"], "12345")
        self.assertTrue(
            UnitAvailabilityBlock.objects.filter(
                tenant=self.tenant,
                unit=self.unit,
                smoobu_booking_id="12345",
            ).exists()
        )

    def test_create_block_overlap_reservation(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 9, 1),
            check_out=date(2026, 9, 5),
            status=Reservation.Status.EXPECTED,
            booker_name="Guest",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
            room_name="R1",
        )
        response = self.client.post(
            f"/api/v1/reception/units/{self.unit.id}/block/",
            {"check_in": "2026-09-02", "check_out": "2026-09-04"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.integrations.smoobu.blocking_service.SmoobuClient")
    def test_unblock_hospira_block(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        block_row = UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            check_in=date(2026, 8, 4),
            check_out=date(2026, 8, 6),
            smoobu_booking_id="99002",
        )
        response = self.client.delete(
            f"/api/v1/reception/blocks/{block_row.id}/",
            **self.auth,
        )
        self.assertEqual(response.status_code, 204)
        mock_client.cancel_reservation.assert_called_once_with("99002")
        self.assertFalse(UnitAvailabilityBlock.objects.filter(pk=block_row.id).exists())

    @patch(
        "apps.integrations.smoobu.calendar_blocks_service._fetch_external_blocks",
        return_value=[
            {
                "id": None,
                "unit_id": 1,
                "unit_code": "R1",
                "check_in": "2026-08-04",
                "check_out": "2026-08-06",
                "smoobu_booking_id": "88001",
                "reservation_id": None,
                "can_unblock": False,
                "source": "smoobu",
            }
        ],
    )
    def test_cannot_unblock_external_block_id(self, _mock_external):
        response = self.client.delete(
            "/api/v1/reception/blocks/99999/",
            **self.auth,
        )
        self.assertEqual(response.status_code, 404)
