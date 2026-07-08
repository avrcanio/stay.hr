from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.properties.models import Property
from apps.reservations.booking_payout_models import BookingPayoutImport
from apps.tenants.models import Tenant, TenantDomain, TenantMembership

User = get_user_model()

_MINIMAL_CSV = (
    "Type,Booking number,Check-in,Checkout,Guest name,Reservation status,"
    "Currency,Amount,Commission,Payments Service Fee,Net,Payout date,Payout ID\n"
    'Reservation,12345,"Jun 1, 2026","Jun 5, 2026",John Doe,ok,EUR,'
    '100.00,-15.00,-5.00,80.00,"Jun 11, 2026",PAY-TEST-001\n'
)


def _csv_upload(name: str = "payout.csv", payout_id: str = "PAY-TEST-001") -> SimpleUploadedFile:
    content = _MINIMAL_CSV.replace("PAY-TEST-001", payout_id)
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


@override_settings(
    ALLOWED_HOSTS=[
        "admin.stay.hr",
        "booking.payout-scope-a.test",
        "booking.payout-scope-b.test",
        "testserver",
    ],
)
class BookingPayoutImportAdminTenantScopeTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a-payout")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b-payout")
        TenantDomain.objects.create(
            tenant=self.tenant_a,
            domain="booking.payout-scope-a.test",
            domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN,
            is_verified=True,
        )
        TenantDomain.objects.create(
            tenant=self.tenant_b,
            domain="booking.payout-scope-b.test",
            domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN,
            is_verified=True,
        )
        self.prop_a = Property.objects.create(
            tenant=self.tenant_a,
            name="Hotel A",
            slug="hotel-a-payout",
        )
        self.prop_b = Property.objects.create(
            tenant=self.tenant_b,
            name="Hotel B",
            slug="hotel-b-payout",
        )
        self.superuser = User.objects.create_superuser(
            username="super_payout",
            password="test-pass-123",
            email="super@payout.test",
        )
        self.staff_a = User.objects.create_user(
            username="staff_a_payout",
            password="test-pass-123",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff_a, tenant=self.tenant_a)
        self.client = Client()
        self.add_url = reverse("admin:reservations_bookingpayoutimport_add")

    def _login(self, user):
        self.client.force_login(user)

    def _get_add_form_csrf(self, host: str) -> str:
        response = self.client.get(self.add_url, HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        return response.cookies["csrftoken"].value

    def _post_add(
        self,
        *,
        host: str,
        csrf: str,
        property_id: int,
        tenant_id: int | None = None,
        payout_id: str = "PAY-TEST-001",
        user=None,
    ):
        if user is not None:
            self._login(user)
        data = {
            "property_obj": str(property_id),
            "source_file": _csv_upload(payout_id=payout_id),
            "csrfmiddlewaretoken": csrf,
            "_save": "Save",
            "lines-TOTAL_FORMS": "0",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "0",
        }
        if tenant_id is not None:
            data["tenant"] = str(tenant_id)
        return self.client.post(self.add_url, data, HTTP_HOST=host)

    def test_add_form_on_tenant_host_hides_tenant_field(self):
        self._login(self.superuser)
        response = self.client.get(self.add_url, HTTP_HOST="booking.payout-scope-a.test")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="tenant"')
        self.assertContains(response, '<select name="property_obj"')

    def test_add_form_on_platform_host_shows_tenant_field(self):
        self._login(self.superuser)
        response = self.client.get(self.add_url, HTTP_HOST="admin.stay.hr")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="tenant"')

    def test_property_obj_is_dropdown_not_raw_id_on_tenant_host(self):
        self._login(self.superuser)
        response = self.client.get(self.add_url, HTTP_HOST="booking.payout-scope-a.test")
        self.assertContains(response, '<select name="property_obj"')
        self.assertNotContains(response, 'id="lookup_id_property_obj"')

    def test_post_tampering_on_tenant_host_uses_host_tenant(self):
        self._login(self.superuser)
        host = "booking.payout-scope-a.test"
        csrf = self._get_add_form_csrf(host)
        before = BookingPayoutImport.objects.count()
        response = self._post_add(
            host=host,
            csrf=csrf,
            property_id=self.prop_a.id,
            tenant_id=self.tenant_b.id,
            payout_id="PAY-TAMPER-001",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BookingPayoutImport.objects.count(), before + 1)
        created = BookingPayoutImport.objects.latest("pk")
        self.assertEqual(created.tenant_id, self.tenant_a.id)
        self.assertNotEqual(created.tenant_id, self.tenant_b.id)

    def test_change_view_tenant_is_readonly(self):
        import_batch = BookingPayoutImport.objects.create(
            tenant=self.tenant_a,
            property_obj=self.prop_a,
            payout_id="PAY-CHANGE-RO",
            payout_date=date(2026, 6, 11),
            currency="EUR",
            status="parsed",
            source_file=_csv_upload("existing.csv", payout_id="PAY-CHANGE-RO"),
        )
        self._login(self.superuser)
        change_url = reverse(
            "admin:reservations_bookingpayoutimport_change",
            args=[import_batch.pk],
        )
        response = self.client.get(change_url, HTTP_HOST="booking.payout-scope-a.test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="readonly"')
        self.assertNotContains(response, '<select name="tenant"')

    def test_staff_cross_tenant_post_on_platform_host_denied(self):
        self._login(self.staff_a)
        host = "admin.stay.hr"
        csrf = self._get_add_form_csrf(host)
        before = BookingPayoutImport.objects.count()
        response = self._post_add(
            host=host,
            csrf=csrf,
            property_id=self.prop_a.id,
            tenant_id=self.tenant_b.id,
            payout_id="PAY-CROSS-001",
        )
        self.assertEqual(BookingPayoutImport.objects.count(), before)
        self.assertFalse(
            BookingPayoutImport.objects.filter(tenant_id=self.tenant_b.id).exists(),
        )
        if response.status_code == 200:
            self.assertTrue(
                response.context["adminform"].form.errors
                or response.context["errors"],
            )
        else:
            self.assertIn(response.status_code, (403, 500))
