from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.admin.forms import IntegrationConfigAdminForm
from apps.integrations.models import IntegrationConfig
from apps.tenants.constants import PLATFORM_TENANT_SLUG
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class PlatformTenantTests(TestCase):
    def test_platform_tenant_exists_after_migration(self):
        tenant, _created = Tenant.objects.get_or_create(
            slug=PLATFORM_TENANT_SLUG,
            defaults={
                "name": "Stay.hr Platform",
                "is_system": True,
            },
        )
        self.assertTrue(tenant.is_system)

    def test_system_tenant_hidden_from_default_admin_queryset(self):
        from apps.tenants.admin import TenantAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model

        platform = Tenant.objects.create(slug="platform-test", name="Platform", is_system=True)
        hotel = Tenant.objects.create(slug="hotel-test", name="Hotel", is_system=False)
        User = get_user_model()
        user = User.objects.create_superuser("admin", "admin@test.com", "pass")
        request = RequestFactory().get("/admin/tenants/tenant/")
        request.user = user
        admin = TenantAdmin(Tenant, AdminSite())
        qs = admin.get_queryset(request)
        self.assertIn(hotel, qs)
        self.assertNotIn(platform, qs)

    def test_system_tenant_not_deletable_in_admin(self):
        from apps.tenants.admin import TenantAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from django.contrib.auth import get_user_model

        platform = Tenant.objects.create(slug="platform-del", name="Platform", is_system=True)
        User = get_user_model()
        user = User.objects.create_superuser("admin2", "admin2@test.com", "pass")
        request = RequestFactory().get("/admin/tenants/tenant/")
        request.user = user
        admin = TenantAdmin(Tenant, AdminSite())
        self.assertFalse(admin.has_delete_permission(request, platform))


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY, WHATSAPP_ACCESS_TOKEN="test-token")
class IntegrationConfigAdminWhatsAppTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")

    def test_whatsapp_phone_number_id_syncs_routing_key_on_create(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            is_active=True,
        )
        form = IntegrationConfigAdminForm(
            data={
                "tenant": self.tenant.pk,
                "property": "",
                "provider": IntegrationConfig.Provider.WHATSAPP,
                "routing_key": "",
                "is_active": True,
                "phone_number_id": "123456789",
                "display_phone_number": "+385911234567",
                "waba_id": "waba-1",
                "auto_reply": True,
            },
            instance=row,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        config = saved.get_config_dict()
        self.assertEqual(config["phone_number_id"], "123456789")
        self.assertNotIn("access_token", config)
        self.assertEqual(saved.routing_key, "123456789")

    def test_whatsapp_phone_number_id_immutable_on_edit(self):
        row = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="111",
            is_active=True,
        )
        row.set_config_dict({"phone_number_id": "111", "display_phone_number": "+385911"})
        row.save()
        form = IntegrationConfigAdminForm(
            data={
                "tenant": self.tenant.pk,
                "property": "",
                "provider": IntegrationConfig.Provider.WHATSAPP,
                "routing_key": "111",
                "is_active": True,
                "phone_number_id": "999",
                "display_phone_number": "+385911",
                "waba_id": "",
                "auto_reply": False,
            },
            instance=row,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("phone_number_id", form.errors)
