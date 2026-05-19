from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse

from apps.properties.models import Property
from apps.reservations.admin import ReservationAdmin
from apps.reservations.models import Reservation
from apps.tenants.admin import ApiApplicationAdmin, TenantAdmin
from apps.tenants.admin_scope import get_allowed_tenant_ids, user_has_tenant_access
from apps.tenants.models import ApiApplication, Tenant, TenantMembership

User = get_user_model()


class AdminScopeHelperTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.staff = User.objects.create_user(
            username="staff_a",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant_a)
        self.superuser = User.objects.create_superuser(
            username="super",
            password="test-pass-123",
            email="super@stay.hr",
        )

    def _request(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def test_allowed_tenant_ids_for_staff(self):
        ids = get_allowed_tenant_ids(self._request(self.staff))
        self.assertEqual(ids, [self.tenant_a.id])

    def test_allowed_tenant_ids_none_for_superuser(self):
        self.assertIsNone(get_allowed_tenant_ids(self._request(self.superuser)))

    def test_user_has_tenant_access(self):
        request = self._request(self.staff)
        self.assertTrue(user_has_tenant_access(request, self.tenant_a.id))
        self.assertFalse(user_has_tenant_access(request, self.tenant_b.id))


class ReservationAdminScopeTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.prop_a = Property.objects.create(
            tenant=self.tenant_a, name="Hotel A", slug="hotel-a",
        )
        self.prop_b = Property.objects.create(
            tenant=self.tenant_b, name="Hotel B", slug="hotel-b",
        )
        self.res_a = Reservation.objects.create(
            tenant=self.tenant_a,
            property=self.prop_a,
            booking_code="A-001",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            booker_name="Ana A",
        )
        self.res_b = Reservation.objects.create(
            tenant=self.tenant_b,
            property=self.prop_b,
            booking_code="B-001",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            booker_name="Bruno B",
        )
        self.staff = User.objects.create_user(
            username="staff_a",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant_a)
        self.staff_no_tenant = User.objects.create_user(
            username="staff_empty",
            password="test-pass-123",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="super",
            password="test-pass-123",
            email="super@stay.hr",
        )
        self.admin = ReservationAdmin(Reservation, None)

    def _request(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def test_staff_sees_only_own_tenant_reservations(self):
        qs = self.admin.get_queryset(self._request(self.staff))
        self.assertEqual(list(qs), [self.res_a])

    def test_superuser_sees_all_reservations(self):
        qs = self.admin.get_queryset(self._request(self.superuser))
        self.assertEqual(qs.count(), 2)

    def test_staff_without_membership_sees_none(self):
        qs = self.admin.get_queryset(self._request(self.staff_no_tenant))
        self.assertEqual(qs.count(), 0)

    def test_staff_cannot_change_other_tenant_object(self):
        self.assertFalse(
            self.admin.has_change_permission(self._request(self.staff), self.res_b),
        )

    def test_enforce_tenant_raises_on_wrong_tenant(self):
        obj = Reservation(
            tenant=self.tenant_b,
            property=self.prop_b,
            booking_code="X-001",
            check_in=date(2026, 7, 1),
            check_out=date(2026, 7, 3),
            booker_name="Hacker",
        )
        with self.assertRaises(PermissionDenied):
            self.admin._enforce_tenant_on_save(self._request(self.staff), obj)


class TenantAdminSuperuserOnlyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", slug="t")
        self.staff = User.objects.create_user(
            username="staff",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant)
        self.superuser = User.objects.create_superuser(
            username="super",
            password="test-pass-123",
            email="super@stay.hr",
        )
        self.admin = TenantAdmin(Tenant, None)

    def _request(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def test_staff_cannot_access_tenant_module(self):
        self.assertFalse(self.admin.has_module_permission(self._request(self.staff)))

    def test_superuser_can_access_tenant_module(self):
        self.assertTrue(self.admin.has_module_permission(self._request(self.superuser)))


class AdminChangelistIntegrationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.prop_a = Property.objects.create(
            tenant=self.tenant_a, name="Hotel A", slug="hotel-a",
        )
        self.prop_b = Property.objects.create(
            tenant=self.tenant_b, name="Hotel B", slug="hotel-b",
        )
        Reservation.objects.create(
            tenant=self.tenant_a,
            property=self.prop_a,
            booking_code="A-001",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            booker_name="Ana A",
        )
        Reservation.objects.create(
            tenant=self.tenant_b,
            property=self.prop_b,
            booking_code="B-001",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 5),
            booker_name="Bruno B",
        )
        self.staff = User.objects.create_user(
            username="staff_a",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant_a)
        self.client = Client()

    def test_changelist_hides_other_tenant_rows(self):
        self.client.force_login(self.staff)
        url = reverse("admin:reservations_reservation_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A-001")
        self.assertNotContains(response, "B-001")


class ApiApplicationAdminScopeTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.app_a, _ = ApiApplication.create_with_token(
            tenant=self.tenant_a,
            name="Tablet A",
            scopes=["reception:read"],
        )
        self.app_b, _ = ApiApplication.create_with_token(
            tenant=self.tenant_b,
            name="Tablet B",
            scopes=["reception:read"],
        )
        self.staff = User.objects.create_user(
            username="staff_a",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant_a)
        self.admin = ApiApplicationAdmin(ApiApplication, None)

    def _request(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def test_staff_sees_only_own_api_apps(self):
        qs = self.admin.get_queryset(self._request(self.staff))
        self.assertEqual(list(qs), [self.app_a])
