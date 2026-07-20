from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.integrations.channex.reservation_availability_service import (
    PROPERTY_CLOSE_BLOCK_REF_PREFIX,
    UZORITA_WHOLE_PROPERTY_UNIT_CODES,
    compute_unit_availability,
    force_close_property_channex_availability,
    mapped_channex_unit_codes_for_property,
    property_whole_close_unit_codes,
    qualifies_for_whole_property_sync,
)
from apps.integrations.models import IntegrationConfig, UnitAvailabilityBlock
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class WholePropertyAvailabilityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
        )
        self.units = {}
        for code in UZORITA_WHOLE_PROPERTY_UNIT_CODES:
            self.units[code] = Unit.objects.create(
                tenant=self.tenant,
                property=self.property,
                code=code,
                name=code,
            )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "property_id": "prop-uzorita",
                "room_types": [
                    {"unit_code": code, "channex_room_type_id": f"rt-{code}"}
                    for code in UZORITA_WHOLE_PROPERTY_UNIT_CODES
                ],
            }
        )
        self.integration.save()

    def test_qualifies_with_two_core_rooms(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 7, 24),
            check_out=date(2026, 7, 25),
            status=Reservation.Status.EXPECTED,
            booker_name="Susanne Mayer",
            units_count=4,
        )
        for sort_order, code in enumerate(("R1", "R3")):
            ReservationUnit.objects.create(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.units[code],
                room_name=code,
                sort_order=sort_order,
            )
        self.assertTrue(qualifies_for_whole_property_sync(reservation))

    def test_does_not_qualify_single_room(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 7, 24),
            check_out=date(2026, 7, 25),
            status=Reservation.Status.EXPECTED,
            booker_name="Pierre",
            units_count=1,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.units["R1"],
            room_name="R1",
        )
        self.assertFalse(qualifies_for_whole_property_sync(reservation))

    def test_uzorita_close_codes_are_whole_property_set(self):
        codes = property_whole_close_unit_codes(
            integration=self.integration,
            property=self.property,
        )
        self.assertEqual(codes, UZORITA_WHOLE_PROPERTY_UNIT_CODES)

    @patch("apps.integrations.channex.reservation_availability_service.apply_availability_updates")
    @patch("apps.integrations.channex.ari_service.push_channex_ari")
    def test_force_close_suspect_blocks_unmapped_listings(self, mock_push, mock_apply):
        mock_apply.return_value = []
        mock_push.return_value = []
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 7, 24),
            check_out=date(2026, 7, 25),
            status=Reservation.Status.EXPECTED,
            booker_name="Philippe",
            units_count=1,
            adults_count=4,
            import_source="channex",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.units["R6"],
            room_name="R6",
        )

        result = force_close_property_channex_availability(
            reservation,
            reason="multi_room_suspect",
        )
        self.assertTrue(result.get("pushed"))
        self.assertTrue(result.get("forced"))

        # Competing listings closed via durable blocks (not held by ReservationUnit).
        for code in ("R1", "R2", "R3"):
            self.assertEqual(
                compute_unit_availability(self.tenant, self.units[code], date(2026, 7, 24)),
                0,
            )
            self.assertTrue(
                UnitAvailabilityBlock.objects.filter(
                    tenant=self.tenant,
                    reservation=reservation,
                    unit=self.units[code],
                    block_ref__startswith=PROPERTY_CLOSE_BLOCK_REF_PREFIX,
                ).exists()
            )
        # Mapped unit closed by occupancy, not a property-close block.
        self.assertEqual(
            compute_unit_availability(self.tenant, self.units["R6"], date(2026, 7, 24)),
            0,
        )
        self.assertFalse(
            UnitAvailabilityBlock.objects.filter(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.units["R6"],
            ).exists()
        )


class GenericPropertyCloseCodesTests(TestCase):
    """Non-Uzorita properties close all Channex-mapped room types."""

    def setUp(self):
        # Generic fixture — not production tenant id 2 / uzorita.
        self.tenant = Tenant.objects.create(slug="demo-close", name="Demo Close")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="demo-villa",
            name="Demo Villa",
            timezone="Europe/Zagreb",
        )
        self.unit_a = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="A1",
            name="A1",
        )
        self.unit_b = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="B1",
            name="B1",
        )
        Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="UNMAPPED",
            name="Unmapped",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "property_id": "prop-demo",
                "room_types": [
                    {"unit_code": "A1", "channex_room_type_id": "rt-a"},
                    {"unit_code": "B1", "channex_room_type_id": "rt-b"},
                ],
            }
        )
        self.integration.save()

    def test_mapped_codes_exclude_unmapped_units(self):
        codes = mapped_channex_unit_codes_for_property(
            integration=self.integration,
            property=self.property,
        )
        self.assertEqual(codes, frozenset({"A1", "B1"}))

    def test_property_close_uses_all_mapped_codes(self):
        codes = property_whole_close_unit_codes(
            integration=self.integration,
            property=self.property,
        )
        self.assertEqual(codes, frozenset({"A1", "B1"}))

    def test_qualifies_without_uzorita_hardcode(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 8, 1),
            check_out=date(2026, 8, 2),
            status=Reservation.Status.EXPECTED,
            booker_name="Guest",
            units_count=2,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_a,
            room_name="A1",
            sort_order=0,
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_b,
            room_name="B1",
            sort_order=1,
        )
        self.assertTrue(
            qualifies_for_whole_property_sync(reservation, self.integration)
        )

    @patch("apps.integrations.channex.reservation_availability_service.apply_availability_updates")
    @patch("apps.integrations.channex.ari_service.push_channex_ari")
    def test_force_close_suspect_closes_all_mapped_room_types(
        self, mock_push, mock_apply
    ):
        """MULTI_ROOM_SUSPECT on any property closes every mapped listing."""
        mock_apply.return_value = []
        mock_push.return_value = []
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 8, 10),
            check_out=date(2026, 8, 11),
            status=Reservation.Status.EXPECTED,
            booker_name="Suspect Guest",
            units_count=1,
            adults_count=4,
            import_source="channex",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit_a,
            room_name="A1",
        )

        result = force_close_property_channex_availability(
            reservation,
            reason="multi_room_suspect",
        )
        self.assertTrue(result.get("pushed"))
        self.assertTrue(result.get("forced"))

        # Mapped unit held by ReservationUnit — closed via occupancy.
        self.assertEqual(
            compute_unit_availability(self.tenant, self.unit_a, date(2026, 8, 10)),
            0,
        )
        self.assertFalse(
            UnitAvailabilityBlock.objects.filter(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.unit_a,
            ).exists()
        )
        # Competing mapped listing closed via durable property-close block.
        self.assertEqual(
            compute_unit_availability(self.tenant, self.unit_b, date(2026, 8, 10)),
            0,
        )
        self.assertTrue(
            UnitAvailabilityBlock.objects.filter(
                tenant=self.tenant,
                reservation=reservation,
                unit=self.unit_b,
                block_ref__startswith=PROPERTY_CLOSE_BLOCK_REF_PREFIX,
            ).exists()
        )
