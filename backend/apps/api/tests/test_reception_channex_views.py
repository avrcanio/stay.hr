from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.integrations.models import ChannelRatePlan, IntegrationConfig, RatePlanDay, UnitAvailabilityDay
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation, ReservationUnit
from apps.tenants.models import ChannelManager, Tenant, TenantMembership, TenantReceptionSettings

User = get_user_model()


class ReceptionChannexViewsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo", name="Demo")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="channex-demo",
            name="Demo",
            timezone="Europe/Zagreb",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="BCOM-STUDIO",
            name="Studio",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "property_id": "prop-id",
                "certification_property_slug": "channex-demo",
                "sync_property_slug": "channex-demo",
                "use_generated_ari": False,
                "booking_test_rooms": [
                    {
                        "unit_code": "BCOM-STUDIO",
                        "channex_room_type_id": "rt-1",
                        "rate_plans": [
                            {
                                "code": "standard",
                                "channex_rate_plan_id": "rp-1",
                                "default_gbp": "95.00",
                            }
                        ],
                    }
                ],
            }
        )
        self.integration.save()

        self.staff = User.objects.create_user(
            username="evan",
            password="secret-pass",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant)
        self.client = APIClient()

    def _login(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "evan", "password": "secret-pass"},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)

    def test_channel_status_requires_channex_tenant(self):
        self._login()
        response = self.client.get(
            "/api/v1/reception/channel/status/",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["channel_manager"], ChannelManager.CHANNEX)

    @patch("apps.api.reception_channex_views.push_channex_ari")
    @patch("apps.api.reception_channex_views.build_full_sync")
    @patch("apps.api.reception_channex_views.seed_channel_rate_plans_from_config")
    def test_full_sync_returns_push_results(self, mock_seed, mock_build, mock_push):
        mock_seed.return_value = 0
        mock_build.return_value = ([{"availability": 1}], [{"rate": "95"}])
        mock_push.return_value = [{"outbox_id": 1, "task_ids": ["task-1"]}]
        self._login()
        response = self.client.post(
            "/api/v1/reception/channel/full-sync/",
            {"days": 500},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["availability_value_batches"], 1)
        self.assertEqual(data["restrictions_value_batches"], 1)
        self.assertEqual(data["push_results"][0]["task_ids"], ["task-1"])

    def test_get_rate_plans_seeds_and_returns(self):
        self._login()
        response = self.client.get(
            "/api/v1/reception/channel/rate-plans/",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        row = data["results"][0]
        self.assertEqual(row["unit_code"], "BCOM-STUDIO")
        self.assertEqual(row["code"], "standard")
        self.assertEqual(row["default_rate"], "95.00")
        self.assertEqual(row["currency"], "GBP")
        self.assertIn("obp", row)
        self.assertEqual(row["obp"]["base_adults"], 1)
        self.assertEqual(row["obp"]["adult_delta"], "5.00")
        self.assertEqual(row["obp"]["child_fee"], "2.00")
        self.assertTrue(
            ChannelRatePlan.objects.filter(
                tenant=self.tenant,
                unit=self.unit,
                code="standard",
            ).exists()
        )

    def test_patch_rate_plans_updates_default_rate(self):
        self._login()
        self.client.get(
            "/api/v1/reception/channel/rate-plans/",
            HTTP_HOST="app.stay.hr",
        )
        plan = ChannelRatePlan.objects.get(tenant=self.tenant, unit=self.unit, code="standard")
        response = self.client.patch(
            "/api/v1/reception/channel/rate-plans/",
            {"updates": [{"id": plan.id, "default_rate": "120.50"}]},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["updated"], 1)
        self.assertEqual(data["results"][0]["default_rate"], "120.50")
        plan.refresh_from_db()
        self.assertEqual(plan.default_rate, Decimal("120.50"))

    def test_rate_plans_403_for_non_channex_tenant(self):
        uzorita = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=uzorita,
            channel_manager=ChannelManager.NONE,
        )
        staff = User.objects.create_user(username="uz_staff2", password="secret-pass", is_staff=True)
        TenantMembership.objects.create(user=staff, tenant=uzorita)
        self.client.post(
            "/api/v1/auth/reception-login/",
            {
                "username": "uz_staff2",
                "password": "secret-pass",
                "tenant_id": uzorita.pk,
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        response = self.client.get(
            "/api/v1/reception/channel/rate-plans/",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.api.reception_channex_views.push_channex_ari")
    def test_inventory_full_sync_uses_updated_default_rate(self, mock_push):
        mock_push.return_value = [{"outbox_id": 1, "task_ids": ["task-1"]}]
        self._login()
        self.client.get(
            "/api/v1/reception/channel/rate-plans/",
            HTTP_HOST="app.stay.hr",
        )
        plan = ChannelRatePlan.objects.get(tenant=self.tenant, unit=self.unit, code="standard")
        self.client.patch(
            "/api/v1/reception/channel/rate-plans/",
            {"updates": [{"id": plan.id, "default_rate": "88.00"}]},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        response = self.client.post(
            "/api/v1/reception/channel/full-sync/",
            {"days": 3},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        sample_day = RatePlanDay.objects.filter(rate_plan=plan).first()
        self.assertIsNotNone(sample_day)
        self.assertEqual(sample_day.rate, Decimal("88.00"))

    def test_get_calendar_channel_ari_returns_availability_and_rates(self):
        self._login()
        self.client.get(
            "/api/v1/reception/channel/rate-plans/",
            HTTP_HOST="app.stay.hr",
        )
        plan = ChannelRatePlan.objects.get(tenant=self.tenant, unit=self.unit, code="standard")
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 15),
            availability=1,
        )
        RatePlanDay.objects.create(
            tenant=self.tenant,
            rate_plan=plan,
            date=date(2026, 6, 15),
            rate=Decimal("95.00"),
            min_stay_arrival=1,
            min_stay_through=1,
            max_stay=30,
            stop_sell=False,
            closed_to_arrival=False,
            closed_to_departure=False,
        )
        response = self.client.get(
            "/api/v1/reception/calendar/channel-ari/?from=2026-06-01&to=2026-07-01",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["availability"]), 1)
        self.assertEqual(data["availability"][0]["unit_id"], self.unit.id)
        self.assertEqual(data["availability"][0]["availability"], 1)
        self.assertEqual(len(data["rates"]), 1)
        self.assertEqual(data["rates"][0]["rate_plan_code"], "standard")
        self.assertEqual(data["rates"][0]["rate"], "95.00")
        self.assertIn("obp_tiers", data["rates"][0])
        self.assertEqual(len(data["rates"][0]["obp_tiers"]), 2)
        self.assertEqual(data["rates"][0]["obp_tiers"][0]["adults"], 1)
        self.assertEqual(data["rates"][0]["obp_tiers"][0]["rate"], "95.00")
        self.assertEqual(data["rates"][0]["obp_tiers"][1]["adults"], 2)
        self.assertEqual(data["rates"][0]["obp_tiers"][1]["rate"], "100.00")
        self.assertEqual(data["rates"][0]["obp_primary_occupancy_adults"], 2)
        self.assertEqual(data["rates"][0]["obp_anchor_adults"], 2)
        self.assertEqual(data["rates"][0]["obp_normal_rate"], "100.00")
        self.assertEqual(data["rates"][0]["channex_push_rate"], "100.00")

    def test_calendar_channel_ari_requires_from_and_to(self):
        self._login()
        response = self.client.get(
            "/api/v1/reception/calendar/channel-ari/",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 400)

    def test_calendar_channel_ari_403_for_non_channex_tenant(self):
        uzorita = Tenant.objects.create(slug="uzorita2", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=uzorita,
            channel_manager=ChannelManager.NONE,
        )
        staff = User.objects.create_user(username="uz_staff3", password="secret-pass", is_staff=True)
        TenantMembership.objects.create(user=staff, tenant=uzorita)
        self.client.post(
            "/api/v1/auth/reception-login/",
            {
                "username": "uz_staff3",
                "password": "secret-pass",
                "tenant_id": uzorita.pk,
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        response = self.client.get(
            "/api/v1/reception/calendar/channel-ari/?from=2026-06-01&to=2026-07-01",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 403)

    def test_create_reservation_via_reception(self):
        self._login()
        response = self.client.post(
            "/api/v1/reception/reservations/create/",
            {
                "property_slug": "channex-demo",
                "unit_id": self.unit.id,
                "check_in": "2026-12-01",
                "check_out": "2026-12-03",
                "booker_name": "Evan Guest",
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["booker_name"], "Evan Guest")

    def test_create_reservation_rejected_when_ari_closed(self):
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 12, 1),
            availability=0,
        )
        self._login()
        response = self.client.post(
            "/api/v1/reception/reservations/create/",
            {
                "property_slug": "channex-demo",
                "unit_id": self.unit.id,
                "check_in": "2026-12-01",
                "check_out": "2026-12-03",
                "booker_name": "Blocked Guest",
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not available", str(response.json()).lower())

    def test_unit_availability_returns_blocked_ari_nights(self):
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 12, 5),
            availability=0,
        )
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 12, 7),
            availability=1,
        )
        self._login()
        response = self.client.get(
            "/api/v1/reception/units/{}/availability/?from=2026-12-01&to=2026-12-10".format(
                self.unit.id
            ),
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["unit_id"], self.unit.id)
        self.assertEqual(data["blocked_nights"], ["2026-12-05"])

    def test_none_tenant_gets_403_on_channel_endpoints(self):
        uzorita = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=uzorita,
            channel_manager=ChannelManager.NONE,
        )
        staff = User.objects.create_user(username="uz_staff", password="secret-pass", is_staff=True)
        TenantMembership.objects.create(user=staff, tenant=uzorita)
        self.client.post(
            "/api/v1/auth/reception-login/",
            {
                "username": "uz_staff",
                "password": "secret-pass",
                "tenant_id": uzorita.pk,
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        response = self.client.post(
            "/api/v1/reception/channel/full-sync/",
            {"days": 500},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.api.reception_channex_views.push_channex_ari")
    def test_bulk_apply_updates_rates_and_pushes(self, mock_push):
        mock_push.return_value = [
            {"outbox_id": 1, "kind": "restrictions", "task_ids": ["task-r1"]},
        ]
        self._login()
        self.client.get(
            "/api/v1/reception/channel/rate-plans/",
            HTTP_HOST="app.stay.hr",
        )
        response = self.client.post(
            "/api/v1/reception/channel/bulk-apply/",
            {
                "unit_code": "BCOM-STUDIO",
                "date_from": "2026-06-01",
                "date_to": "2026-06-05",
                "rates": [{"rate_plan_code": "standard", "rate": "99.00", "min_stay_arrival": 2}],
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["rate_days_updated"], 0)
        self.assertEqual(data["availability_days_updated"], 0)
        self.assertEqual(data["push_results"][0]["task_ids"], ["task-r1"])
        plan = ChannelRatePlan.objects.get(tenant=self.tenant, unit=self.unit, code="standard")
        day = RatePlanDay.objects.get(rate_plan=plan, date=date(2026, 6, 3))
        self.assertEqual(day.rate, Decimal("99.00"))
        self.assertEqual(day.min_stay_arrival, 2)

    @patch("apps.api.reception_channex_views.push_channex_ari")
    def test_bulk_apply_availability(self, mock_push):
        mock_push.return_value = [
            {"outbox_id": 2, "kind": "availability", "task_ids": ["task-a1"]},
        ]
        self._login()
        response = self.client.post(
            "/api/v1/reception/channel/bulk-apply/",
            {
                "unit_code": "BCOM-STUDIO",
                "date_from": "2026-06-10",
                "date_to": "2026-06-12",
                "rates": [],
                "availability": 1,
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["rate_days_updated"], 0)
        self.assertEqual(data["availability_days_updated"], 3)
        self.assertEqual(data["protected_nights"], [])
        row = UnitAvailabilityDay.objects.get(unit=self.unit, date=date(2026, 6, 11))
        self.assertEqual(row.availability, 1)

    @patch("apps.api.reception_channex_views.push_channex_ari")
    def test_bulk_apply_open_skips_nights_with_reservation(self, mock_push):
        mock_push.return_value = [
            {"outbox_id": 2, "kind": "availability", "task_ids": ["task-a1"]},
        ]
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 6, 11),
            check_out=date(2026, 6, 13),
            booker_name="Guest",
            status=Reservation.Status.EXPECTED,
            source="reception",
            import_source="manual",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
            sort_order=0,
            room_name="Studio",
        )
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 11),
            availability=0,
        )
        UnitAvailabilityDay.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            date=date(2026, 6, 12),
            availability=0,
        )
        self._login()
        response = self.client.post(
            "/api/v1/reception/channel/bulk-apply/",
            {
                "unit_code": "BCOM-STUDIO",
                "date_from": "2026-06-10",
                "date_to": "2026-06-12",
                "rates": [],
                "availability": 1,
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data["protected_nights"],
            [{"unit_code": "BCOM-STUDIO", "dates": ["2026-06-11", "2026-06-12"]}],
        )
        self.assertEqual(
            UnitAvailabilityDay.objects.get(unit=self.unit, date=date(2026, 6, 10)).availability,
            1,
        )
        self.assertEqual(
            UnitAvailabilityDay.objects.get(unit=self.unit, date=date(2026, 6, 11)).availability,
            0,
        )
        self.assertEqual(
            UnitAvailabilityDay.objects.get(unit=self.unit, date=date(2026, 6, 12)).availability,
            0,
        )

    @patch("apps.api.reception_channex_views.push_channex_ari")
    def test_bulk_apply_close_with_reservation(self, mock_push):
        mock_push.return_value = [
            {"outbox_id": 2, "kind": "availability", "task_ids": ["task-a1"]},
        ]
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 6, 11),
            check_out=date(2026, 6, 13),
            booker_name="Guest",
            status=Reservation.Status.EXPECTED,
            source="reception",
            import_source="manual",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=self.unit,
            sort_order=0,
            room_name="Studio",
        )
        self._login()
        response = self.client.post(
            "/api/v1/reception/channel/bulk-apply/",
            {
                "unit_code": "BCOM-STUDIO",
                "date_from": "2026-06-10",
                "date_to": "2026-06-12",
                "rates": [],
                "availability": 0,
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["protected_nights"], [])
        for day in (date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)):
            self.assertEqual(
                UnitAvailabilityDay.objects.get(unit=self.unit, date=day).availability,
                0,
            )

    def test_bulk_apply_empty_payload_400(self):
        self._login()
        response = self.client.post(
            "/api/v1/reception/channel/bulk-apply/",
            {
                "unit_code": "BCOM-STUDIO",
                "date_from": "2026-06-01",
                "date_to": "2026-06-02",
                "rates": [],
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_apply_403_for_non_channex_tenant(self):
        uzorita = Tenant.objects.create(slug="uzorita-bulk", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=uzorita,
            channel_manager=ChannelManager.NONE,
        )
        staff = User.objects.create_user(username="uz_bulk", password="secret-pass", is_staff=True)
        TenantMembership.objects.create(user=staff, tenant=uzorita)
        self.client.post(
            "/api/v1/auth/reception-login/",
            {
                "username": "uz_bulk",
                "password": "secret-pass",
                "tenant_id": uzorita.pk,
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        response = self.client.post(
            "/api/v1/reception/channel/bulk-apply/",
            {
                "unit_code": "BCOM-STUDIO",
                "date_from": "2026-06-01",
                "date_to": "2026-06-02",
                "rates": [{"rate_plan_code": "standard", "rate": "90.00"}],
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.api.reception_channex_views.push_channex_ari")
    def test_bulk_apply_multiple_units(self, mock_push):
        mock_push.return_value = [{"outbox_id": 1, "task_ids": ["task-multi"]}]
        holiday = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="BCOM-HOLIDAY",
            name="Holiday",
        )
        self._login()
        config = self.integration.get_config_dict()
        config["booking_test_rooms"].append(
            {
                "unit_code": "BCOM-HOLIDAY",
                "channex_room_type_id": "rt-2",
                "rate_plans": [
                    {
                        "code": "standard",
                        "channex_rate_plan_id": "rp-2",
                        "default_gbp": "120.00",
                    }
                ],
            }
        )
        self.integration.set_config_dict(config)
        self.integration.save()
        self.client.get(
            "/api/v1/reception/channel/rate-plans/",
            HTTP_HOST="app.stay.hr",
        )
        response = self.client.post(
            "/api/v1/reception/channel/bulk-apply/",
            {
                "unit_codes": ["BCOM-STUDIO", "BCOM-HOLIDAY"],
                "date_from": "2026-07-01",
                "date_to": "2026-07-03",
                "rates": [{"rate_plan_code": "standard", "rate": "101.00"}],
            },
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["rate_days_updated"], 6)
        studio_plan = ChannelRatePlan.objects.get(
            tenant=self.tenant, unit=self.unit, code="standard"
        )
        holiday_plan = ChannelRatePlan.objects.get(
            tenant=self.tenant, unit=holiday, code="standard"
        )
        self.assertEqual(
            RatePlanDay.objects.get(rate_plan=studio_plan, date=date(2026, 7, 2)).rate,
            Decimal("101.00"),
        )
        self.assertEqual(
            RatePlanDay.objects.get(rate_plan=holiday_plan, date=date(2026, 7, 2)).rate,
            Decimal("101.00"),
        )
