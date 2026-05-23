from unittest.mock import MagicMock, patch

from django.test import RequestFactory, TestCase, override_settings

from apps.api.site_context_views import SiteContextView
from apps.properties.models import Property
from apps.tenants.cloudflare.dns import apex_zone_name, zone_name_for_tenant_domain
from apps.tenants.middleware import TenantHostMiddleware, resolve_tenant_host
from apps.tenants.models import Tenant, TenantDomain


class SiteContextViewTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Uzorita",
            slug="uzorita",
            default_language="hr",
        )
        self.property_obj = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita Luxury Rooms",
            slug="uzorita",
            branding={"primary_color": "#123456"},
        )
        self.tenant_domain = TenantDomain.objects.create(
            tenant=self.tenant,
            property=self.property_obj,
            domain="booking.uzorita.hr",
            domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN,
            is_verified=True,
        )
        self.factory = RequestFactory()

    def test_site_context_returns_tenant_and_property(self):
        request = self.factory.get(
            "/api/v1/public/site-context/",
            HTTP_HOST="booking.uzorita.hr",
        )
        request.tenant = self.tenant
        request.tenant_domain = self.tenant_domain

        response = SiteContextView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tenant"]["slug"], "uzorita")
        self.assertEqual(response.data["property"]["slug"], "uzorita")
        self.assertEqual(response.data["branding"]["primary_color"], "#123456")
        self.assertEqual(response.data["languages"], ["hr", "en", "es", "fr", "de", "it"])
        self.assertEqual(response.data["default_language"], "hr")

    def test_site_context_unknown_host_returns_404(self):
        request = self.factory.get("/api/v1/public/site-context/", HTTP_HOST="unknown.example")
        response = SiteContextView.as_view()(request)
        self.assertEqual(response.status_code, 404)

    def test_middleware_resolves_host_from_x_forwarded_on_internal_bff(self):
        request = self.factory.get(
            "/api/v1/public/site-context/",
            HTTP_HOST="stay-django:8000",
            HTTP_X_FORWARDED_HOST="booking.uzorita.hr",
        )
        TenantHostMiddleware(lambda req: req)(request)
        self.assertEqual(request.tenant.slug, "uzorita")
        self.assertEqual(request.tenant_domain.domain, "booking.uzorita.hr")

    def test_resolve_tenant_host_prefers_forwarded_on_internal(self):
        request = self.factory.get(
            "/",
            HTTP_HOST="stay-django",
            HTTP_X_FORWARDED_HOST="booking.uzorita.hr",
        )
        self.assertEqual(resolve_tenant_host(request), "booking.uzorita.hr")


class CloudflareDnsHelperTests(TestCase):
    def test_apex_zone_name(self):
        self.assertEqual(apex_zone_name("booking.uzorita.hr"), "uzorita.hr")
        self.assertEqual(apex_zone_name("demo.stay.hr"), "stay.hr")

    def test_zone_name_for_tenant_domain(self):
        tenant = Tenant.objects.create(name="Demo", slug="demo")
        stay_domain = TenantDomain(
            tenant=tenant,
            domain="demo.stay.hr",
            domain_type=TenantDomain.DomainType.STAY_SUBDOMAIN,
        )
        custom_domain = TenantDomain(
            tenant=tenant,
            domain="booking.example.com",
            domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN,
        )

        with override_settings(CLOUDFLARE_ZONE_STAY="stay.hr"):
            self.assertEqual(zone_name_for_tenant_domain(stay_domain), "stay.hr")
            self.assertEqual(zone_name_for_tenant_domain(custom_domain), "example.com")


@override_settings(
    CF_DNS_API_TOKEN="test-token",
    STAY_SERVER_IP="203.0.113.10",
    CLOUDFLARE_ZONE_STAY="stay.hr",
)
class ProvisionPlatformDnsTests(TestCase):
    @patch("apps.tenants.cloudflare.dns.CloudflareClient")
    def test_provision_platform_dns_upserts_records(self, client_cls):
        client = MagicMock()
        client_cls.return_value = client
        client.get_zone_id.return_value = "zone123"

        from apps.tenants.cloudflare.dns import provision_platform_dns

        records = provision_platform_dns()

        client.verify_token.assert_called_once()
        self.assertEqual(client.upsert_a_record.call_count, 2)
        client.upsert_a_record.assert_any_call(
            "zone123",
            "app.stay.hr",
            "203.0.113.10",
            proxied=True,
        )
        client.upsert_a_record.assert_any_call(
            "zone123",
            "*.stay.hr",
            "203.0.113.10",
            proxied=True,
        )
        self.assertEqual(len(records), 2)
