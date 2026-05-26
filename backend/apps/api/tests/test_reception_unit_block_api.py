from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations.models import UnitAvailabilityBlock
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import (
    RECEPTION_DEVICE_SCOPES,
    ApiApplication,
    ChannelManager,
    Tenant,
    TenantReceptionSettings,
)


class ReceptionUnitBlockAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.NONE,
        )
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
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_list_blocks_requires_from_to(self):
        response = self.client.get("/api/v1/reception/calendar/blocks/", **self.auth)
        self.assertEqual(response.status_code, 400)

    def test_list_stay_blocks(self):
        UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            check_in=date(2026, 8, 4),
            check_out=date(2026, 8, 6),
            block_ref="local:test1",
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
        self.assertEqual(data[0]["source"], "stay")
        self.assertIsNone(data[0]["reservation_id"])

    def test_list_stay_blocks_includes_reservation_id(self):
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
            block_ref="140631922",
        )
        response = self.client.get(
            "/api/v1/reception/calendar/blocks/?from=2026-10-01&to=2026-10-31",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["reservation_id"], reservation.id)
        self.assertFalse(data[0]["can_unblock"])

    def test_create_block(self):
        response = self.client.post(
            f"/api/v1/reception/units/{self.unit.id}/block/",
            {"check_in": "2026-09-01", "check_out": "2026-09-04"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["block_ref"].startswith("local:"))
        self.assertTrue(
            UnitAvailabilityBlock.objects.filter(
                tenant=self.tenant,
                unit=self.unit,
                block_ref=payload["block_ref"],
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

    def test_unblock_stay_block(self):
        block_row = UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            check_in=date(2026, 8, 4),
            check_out=date(2026, 8, 6),
            block_ref="local:test2",
        )
        response = self.client.delete(
            f"/api/v1/reception/blocks/{block_row.id}/",
            **self.auth,
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(UnitAvailabilityBlock.objects.filter(pk=block_row.id).exists())

    def test_cannot_unblock_reservation_linked_block(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 8, 4),
            check_out=date(2026, 8, 6),
            status=Reservation.Status.EXPECTED,
            booker_name="Guest",
        )
        block_row = UnitAvailabilityBlock.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reservation=reservation,
            check_in=date(2026, 8, 4),
            check_out=date(2026, 8, 6),
            block_ref="local:test3",
        )
        response = self.client.delete(
            f"/api/v1/reception/blocks/{block_row.id}/",
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(UnitAvailabilityBlock.objects.filter(pk=block_row.id).exists())

    @patch("apps.integrations.channex.ari_service.push_channex_ari")
    @patch("apps.integrations.channex.reservation_availability_service.push_availability_range_for_unit")
    def test_channex_create_block_pushes_availability(self, mock_range, mock_push):
        from apps.integrations.models import IntegrationConfig

        TenantReceptionSettings.objects.filter(tenant=self.tenant).update(
            channel_manager=ChannelManager.CHANNEX
        )
        channex = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        channex.set_config_dict(
            {
                "property_id": "prop-id",
                "room_types": [{"unit_code": "R1", "channex_room_type_id": "rt-1"}],
            }
        )
        channex.save()
        mock_range.return_value = {"pushed": True}
        mock_push.return_value = []

        response = self.client.post(
            f"/api/v1/reception/units/{self.unit.id}/block/",
            {"check_in": "2026-09-01", "check_out": "2026-09-04"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json().get("channex_pushed"))
