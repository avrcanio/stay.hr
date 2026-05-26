from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import (
    RECEPTION_DEVICE_SCOPES,
    ApiApplication,
    StaffLoginEvent,
    Tenant,
    TenantMembership,
)

User = get_user_model()


class ReceptionStaffAuthTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.tenant_b = Tenant.objects.create(name="Demo", slug="demo")
        self.property = Property.objects.create(
            tenant=self.tenant_a,
            name="Uzorita",
            slug="uzorita",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant_a,
            property=self.property,
            code="101",
            name="Soba 101",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant_a,
            property=self.property,
            external_id="ext-1",
            booking_code="BK-1",
            check_in=date(2026, 5, 10),
            check_out=date(2026, 5, 15),
            status=Reservation.Status.EXPECTED,
            booker_name="Ana Anić",
            amount=Decimal("120.00"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant_a,
            reservation=self.reservation,
            unit=self.unit,
            room_name="Soba 101",
            sort_order=0,
        )
        Guest.objects.create(
            tenant=self.tenant_a,
            reservation=self.reservation,
            first_name="Marko",
            last_name="Marković",
            is_primary=True,
        )

        self.staff = User.objects.create_user(
            username="reception_staff",
            password="secret-pass",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant_a)

        self.multi_staff = User.objects.create_user(
            username="multi_staff",
            password="secret-pass",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.multi_staff, tenant=self.tenant_a)
        TenantMembership.objects.create(user=self.multi_staff, tenant=self.tenant_b)

        self.non_staff = User.objects.create_user(
            username="guest_user",
            password="secret-pass",
            is_staff=False,
        )

        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant_a,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )

        self.client = APIClient()

    def test_login_success_single_tenant(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["tenant"]["slug"], "uzorita")
        self.assertEqual(data["user"]["username"], "reception_staff")
        self.assertEqual(data["user"]["preferred_language"], "hr")

    def test_login_returns_user_preferred_language(self):
        from apps.tenants.models import StaffProfile

        StaffProfile.objects.create(user=self.staff, preferred_language="en")
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["preferred_language"], "en")

    def test_login_invalid_password(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_login_non_staff_forbidden(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "guest_user", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_login_multiple_tenants_requires_selection(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "multi_staff", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertTrue(data["requires_tenant"])
        self.assertEqual(len(data["tenants"]), 2)

    def test_login_with_tenant_id(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {
                "username": "multi_staff",
                "password": "secret-pass",
                "tenant_id": self.tenant_b.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenant"]["slug"], "demo")

    def test_session_endpoint_after_login(self):
        self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "secret-pass"},
            format="json",
        )
        response = self.client.get("/api/v1/auth/reception-session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenant"]["slug"], "uzorita")
        self.assertEqual(response.json()["user"]["preferred_language"], "hr")

    def test_logout_clears_session(self):
        self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "secret-pass"},
            format="json",
        )
        response = self.client.post("/api/v1/auth/reception-logout/")
        self.assertEqual(response.status_code, 204)
        response = self.client.get("/api/v1/auth/reception-session/")
        self.assertEqual(response.status_code, 403)

    def test_reception_timeline_with_session(self):
        self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "secret-pass"},
            format="json",
        )
        response = self.client.get("/api/v1/reception/reservations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_app_config_with_session(self):
        self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "secret-pass"},
            format="json",
        )
        response = self.client.get(
            "/api/v1/app/config",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenant"]["slug"], "uzorita")

    def test_reception_timeline_with_bearer_token_regression(self):
        response = self.client.get(
            "/api/v1/reception/reservations/",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_unauthenticated_reception_timeline_forbidden(self):
        response = self.client.get("/api/v1/reception/reservations/")
        self.assertEqual(response.status_code, 403)

    def test_reception_login_records_single_event(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "reception_staff", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        events = StaffLoginEvent.objects.filter(user=self.staff)
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.channel, StaffLoginEvent.Channel.RECEPTION)
        self.assertEqual(event.tenant_id, self.tenant_a.pk)
        self.assertEqual(event.username, "reception_staff")

    def test_reception_login_with_tenant_records_event(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {
                "username": "multi_staff",
                "password": "secret-pass",
                "tenant_id": self.tenant_b.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        event = StaffLoginEvent.objects.get(user=self.multi_staff)
        self.assertEqual(event.channel, StaffLoginEvent.Channel.RECEPTION)
        self.assertEqual(event.tenant_id, self.tenant_b.pk)

    def test_reception_login_requires_tenant_does_not_record_event(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "multi_staff", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(StaffLoginEvent.objects.filter(user=self.multi_staff).count(), 0)

    def test_admin_login_records_event(self):
        admin_user = User.objects.create_superuser(
            username="admin_test",
            password="secret-pass",
            email="admin@test.com",
        )
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": "admin_test",
                "password": "secret-pass",
                "next": "/admin/",
            },
        )
        self.assertIn(response.status_code, (302, 200))
        events = StaffLoginEvent.objects.filter(user=admin_user, channel=StaffLoginEvent.Channel.ADMIN)
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.username, "admin_test")
