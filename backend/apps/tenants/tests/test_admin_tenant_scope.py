from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotFound
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.properties.models import Property
from apps.reservations.admin import ReservationAdmin
from apps.reservations.booking_payout_admin import BookingPayoutImportAdmin
from apps.reservations.booking_payout_models import BookingPayoutImport
from apps.reservations.models import Reservation
from apps.tenants.admin import ApiApplicationAdmin, TenantAdmin
from apps.tenants.admin_scope import (
    AdminScope,
    get_allowed_tenant_ids,
    is_platform_admin,
    resolve_admin_scope,
    user_has_tenant_access,
)
from apps.tenants.middleware import AdminTenantHostGuardMiddleware, TenantHostMiddleware
from apps.tenants.models import ApiApplication, Tenant, TenantDomain, TenantMembership

User = get_user_model()


class AdminScopeHelperTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        TenantDomain.objects.create(
            tenant=self.tenant_a,
            domain="tenant-a.stay.hr",
            domain_type=TenantDomain.DomainType.STAY_SUBDOMAIN,
            is_verified=True,
        )
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
        self.factory = RequestFactory()

    def _request(self, user, host="admin.stay.hr", tenant=None):
        request = self.factory.get("/admin/", HTTP_HOST=host)
        request.user = user
        request.tenant = tenant
        return request

    def test_allowed_tenant_ids_for_staff_on_platform_host(self):
        ids = get_allowed_tenant_ids(self._request(self.staff))
        self.assertEqual(ids, [self.tenant_a.id])

    def test_allowed_tenant_ids_none_for_superuser_on_platform_host(self):
        self.assertIsNone(get_allowed_tenant_ids(self._request(self.superuser)))

    def test_user_has_tenant_access(self):
        request = self._request(self.staff)
        self.assertTrue(user_has_tenant_access(request, self.tenant_a.id))
        self.assertFalse(user_has_tenant_access(request, self.tenant_b.id))

    def test_resolve_admin_scope_platform_host(self):
        scope = resolve_admin_scope(self._request(self.staff))
        self.assertEqual(scope, AdminScope(platform_admin=True, tenant_id=None))

    def test_resolve_admin_scope_tenant_host(self):
        scope = resolve_admin_scope(
            self._request(self.staff, host="tenant-a.stay.hr", tenant=self.tenant_a),
        )
        self.assertEqual(
            scope,
            AdminScope(platform_admin=False, tenant_id=self.tenant_a.id),
        )

    def test_superuser_scoped_to_tenant_host(self):
        request = self._request(
            self.superuser,
            host="tenant-a.stay.hr",
            tenant=self.tenant_a,
        )
        self.assertEqual(get_allowed_tenant_ids(request), [self.tenant_a.id])
        self.assertFalse(is_platform_admin(request))

    def test_staff_on_tenant_host_with_membership(self):
        request = self._request(
            self.staff,
            host="tenant-a.stay.hr",
            tenant=self.tenant_a,
        )
        self.assertEqual(get_allowed_tenant_ids(request), [self.tenant_a.id])

    def test_staff_on_tenant_host_without_membership(self):
        staff_b = User.objects.create_user(
            username="staff_b",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=staff_b, tenant=self.tenant_b)
        request = self._request(
            staff_b,
            host="tenant-a.stay.hr",
            tenant=self.tenant_a,
        )
        self.assertEqual(get_allowed_tenant_ids(request), [])

    def test_unknown_host_admin_scope_has_no_tenant(self):
        scope = resolve_admin_scope(self._request(self.staff, host="unknown.example"))
        self.assertEqual(scope, AdminScope(platform_admin=False, tenant_id=None))
        self.assertEqual(get_allowed_tenant_ids(self._request(self.staff, host="unknown.example")), [])


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
        self.factory = RequestFactory()

    def _request(self, user, host="admin.stay.hr", tenant=None):
        request = self.factory.get("/admin/", HTTP_HOST=host)
        request.user = user
        request.tenant = tenant
        return request

    def test_staff_sees_only_own_tenant_reservations(self):
        qs = self.admin.get_queryset(self._request(self.staff))
        self.assertEqual(list(qs), [self.res_a])

    def test_superuser_sees_all_reservations_on_platform_host(self):
        qs = self.admin.get_queryset(self._request(self.superuser))
        self.assertEqual(qs.count(), 2)

    def test_superuser_on_tenant_host_sees_only_that_tenant(self):
        qs = self.admin.get_queryset(
            self._request(self.superuser, host="tenant-a.stay.hr", tenant=self.tenant_a),
        )
        self.assertEqual(list(qs), [self.res_a])

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

    def _request(self, user, host="admin.stay.hr", tenant=None):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/", HTTP_HOST=host)
        request.user = user
        request.tenant = tenant
        return request

    def test_staff_cannot_access_tenant_module(self):
        self.assertFalse(self.admin.has_module_permission(self._request(self.staff)))

    def test_superuser_can_access_tenant_module_on_platform_host(self):
        self.assertTrue(self.admin.has_module_permission(self._request(self.superuser)))

    def test_superuser_on_tenant_host_cannot_access_tenant_module(self):
        self.assertFalse(
            self.admin.has_module_permission(
                self._request(self.superuser, host="demo.stay.hr", tenant=self.tenant),
            ),
        )


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
        response = self.client.get(url, HTTP_HOST="admin.stay.hr")
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

    def _request(self, user, host="admin.stay.hr", tenant=None):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/", HTTP_HOST=host)
        request.user = user
        request.tenant = tenant
        return request

    def test_staff_sees_only_own_api_apps(self):
        qs = self.admin.get_queryset(self._request(self.staff))
        self.assertEqual(list(qs), [self.app_a])


class AdminTenantHostGuardMiddlewareTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        TenantDomain.objects.create(
            tenant=self.tenant,
            domain="demo.stay.hr",
            domain_type=TenantDomain.DomainType.STAY_SUBDOMAIN,
            is_verified=True,
        )
        self.factory = RequestFactory()
        self.middleware = AdminTenantHostGuardMiddleware(lambda request: request)

    def test_unknown_host_admin_returns_404(self):
        request = self.factory.get("/admin/", HTTP_HOST="unknown.example")
        response = self.middleware(request)
        self.assertIsInstance(response, HttpResponseNotFound)

    def test_platform_admin_host_passes_through(self):
        request = self.factory.get("/admin/", HTTP_HOST="admin.stay.hr")
        response = self.middleware(request)
        self.assertIs(response, request)

    def test_tenant_host_passes_through(self):
        request = self.factory.get("/admin/", HTTP_HOST="demo.stay.hr")
        TenantHostMiddleware(lambda req: req)(request)
        response = self.middleware(request)
        self.assertIs(response, request)

    def test_non_admin_path_skips_guard(self):
        request = self.factory.get("/api/v1/public/site-context/", HTTP_HOST="unknown.example")
        response = self.middleware(request)
        self.assertIs(response, request)


class AdminLoginAuditTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        TenantDomain.objects.create(
            tenant=self.tenant,
            domain="demo.stay.hr",
            domain_type=TenantDomain.DomainType.STAY_SUBDOMAIN,
            is_verified=True,
        )
        self.staff = User.objects.create_user(
            username="staff_demo",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant)
        self.client = Client()

    @override_settings(ALLOWED_HOSTS=["demo.stay.hr", "admin.stay.hr", "testserver"])
    def test_admin_login_records_tenant_from_host(self):
        from apps.tenants.models import StaffLoginEvent
        from apps.tenants.signals import record_admin_staff_login

        request = RequestFactory().get("/admin/", HTTP_HOST="demo.stay.hr")
        TenantHostMiddleware(lambda req: req)(request)
        record_admin_staff_login(sender=None, request=request, user=self.staff)

        event = StaffLoginEvent.objects.get(
            user=self.staff,
            channel=StaffLoginEvent.Channel.ADMIN,
        )
        self.assertEqual(event.tenant_id, self.tenant.id)


class TenantHostScopedAdminMixinTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a-host")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b-host")
        TenantDomain.objects.create(
            tenant=self.tenant_a,
            domain="tenant-a-host.stay.hr",
            domain_type=TenantDomain.DomainType.STAY_SUBDOMAIN,
            is_verified=True,
        )
        self.superuser = User.objects.create_superuser(
            username="super_host",
            password="test-pass-123",
            email="super@stay.hr",
        )
        self.admin = BookingPayoutImportAdmin(BookingPayoutImport, None)
        self.factory = RequestFactory()

    def _request(self, user, host="admin.stay.hr", tenant=None):
        request = self.factory.get("/admin/", HTTP_HOST=host)
        request.user = user
        request.tenant = tenant
        return request

    def test_host_tenant_id_and_is_host_scoped(self):
        platform_request = self._request(self.superuser)
        host_request = self._request(
            self.superuser,
            host="tenant-a-host.stay.hr",
            tenant=self.tenant_a,
        )
        self.assertIsNone(self.admin.host_tenant_id(platform_request))
        self.assertFalse(self.admin.is_host_scoped(platform_request))
        self.assertEqual(self.admin.host_tenant_id(host_request), self.tenant_a.id)
        self.assertTrue(self.admin.is_host_scoped(host_request))

    def test_apply_host_tenant_overwrites_wrong_tenant_on_host(self):
        obj = BookingPayoutImport(tenant_id=self.tenant_b.id)
        request = self._request(
            self.superuser,
            host="tenant-a-host.stay.hr",
            tenant=self.tenant_a,
        )
        self.admin.apply_host_tenant(request, obj)
        self.assertEqual(obj.tenant_id, self.tenant_a.id)

    def test_get_fields_hides_tenant_on_add_for_host_scoped_request(self):
        request = self._request(
            self.superuser,
            host="tenant-a-host.stay.hr",
            tenant=self.tenant_a,
        )
        fields = self.admin.get_fields(request, obj=None)
        self.assertNotIn("tenant", fields)
        self.assertIn("property_obj", fields)

    def test_get_fields_shows_tenant_on_platform_add(self):
        request = self._request(self.superuser)
        fields = self.admin.get_fields(request, obj=None)
        self.assertIn("tenant", fields)

    def test_get_readonly_fields_makes_tenant_readonly_on_change(self):
        prop = Property.objects.create(
            tenant=self.tenant_a,
            name="Hotel A",
            slug="hotel-a-host",
        )
        import_batch = BookingPayoutImport.objects.create(
            tenant=self.tenant_a,
            property_obj=prop,
            payout_id="PAY-RO",
            payout_date=date(2026, 6, 11),
            currency="EUR",
            status="parsed",
            source_file=ContentFile(b"Type\n", name="readonly.csv"),
        )
        request = self._request(
            self.superuser,
            host="tenant-a-host.stay.hr",
            tenant=self.tenant_a,
        )
        readonly = self.admin.get_readonly_fields(request, import_batch)
        self.assertIn("tenant", readonly)

