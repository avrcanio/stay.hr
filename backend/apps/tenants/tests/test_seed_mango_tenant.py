from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from apps.properties.models import Property, Unit
from apps.tenants.mango_html_seed import (
    DOMAIN,
    PROPERTY_SLUG,
    TENANT_SLUG,
    UNIT_CODE,
    DEFAULT_NAME,
    extract_ld_json,
    load_mango_seed_data,
)
from apps.tenants.models import ChannelManager, Tenant, TenantDomain, TenantReceptionSettings

SAMPLE_HTML = """
<html>
<head>
<script type="application/ld+json">
{
   "name" : "Parsed Mango Name",
   "address" : {
      "streetAddress" : "99 Test ulica, Vodice"
   },
   "description" : "Parsed description text.",
   "image" : "https://example.com/hero.jpg"
}
</script>
</head>
</html>
"""


class MangoHtmlSeedTests(TestCase):
    def test_extract_ld_json_parses_nested_object(self):
        payload = extract_ld_json(SAMPLE_HTML)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["name"], "Parsed Mango Name")
        self.assertEqual(payload["address"]["streetAddress"], "99 Test ulica, Vodice")

    def test_load_mango_seed_data_uses_defaults_when_file_missing(self):
        data = load_mango_seed_data(Path("/tmp/does-not-exist-mango.html"))
        self.assertEqual(data.name, DEFAULT_NAME)

    def test_load_mango_seed_data_reads_html_file(self):
        with TemporaryDirectory() as tmp_dir:
            html_file = Path(tmp_dir) / "mango.html"
            html_file.write_text(SAMPLE_HTML, encoding="utf-8")
            data = load_mango_seed_data(html_file)
        self.assertEqual(data.name, "Parsed Mango Name")
        self.assertEqual(data.address, "99 Test ulica, Vodice")
        self.assertEqual(data.description, "Parsed description text.")
        self.assertEqual(data.hero_image_url, "https://example.com/hero.jpg")


class SeedMangoTenantCommandTests(TestCase):
    def _run_seed(self, html_path: str | None = None):
        out = StringIO()
        kwargs = {"stdout": out}
        if html_path is not None:
            kwargs["html_path"] = html_path
        call_command("seed_mango_tenant", **kwargs)
        return out.getvalue()

    def test_seed_creates_tenant_property_unit_and_domain(self):
        self._run_seed(html_path="/tmp/does-not-exist-mango.html")

        tenant = Tenant.objects.get(slug=TENANT_SLUG)
        self.assertEqual(tenant.name, DEFAULT_NAME)
        self.assertEqual(tenant.default_language, "hr")

        settings = TenantReceptionSettings.objects.get(tenant=tenant)
        self.assertEqual(settings.channel_manager, ChannelManager.NONE)

        prop = Property.objects.get(tenant=tenant, slug=PROPERTY_SLUG)
        self.assertEqual(prop.language, "hr")
        self.assertIn("site_title", prop.branding)

        unit = Unit.objects.get(tenant=tenant, property=prop, code=UNIT_CODE)
        self.assertEqual(unit.capacity_max_guests, 7)
        self.assertEqual(unit.capacity_adults, 7)

        domain = TenantDomain.objects.get(domain=DOMAIN)
        self.assertEqual(domain.tenant_id, tenant.id)
        self.assertEqual(domain.property_id, prop.id)
        self.assertFalse(domain.is_verified)

    def test_seed_is_idempotent(self):
        self._run_seed(html_path="/tmp/does-not-exist-mango.html")
        self._run_seed(html_path="/tmp/does-not-exist-mango.html")

        self.assertEqual(Tenant.objects.filter(slug=TENANT_SLUG).count(), 1)
        self.assertEqual(Property.objects.filter(tenant__slug=TENANT_SLUG).count(), 1)
        self.assertEqual(Unit.objects.filter(tenant__slug=TENANT_SLUG).count(), 1)
        self.assertEqual(TenantDomain.objects.filter(domain=DOMAIN).count(), 1)

    def test_seed_uses_html_metadata_when_provided(self):
        with TemporaryDirectory() as tmp_dir:
            html_file = Path(tmp_dir) / "mango.html"
            html_file.write_text(SAMPLE_HTML, encoding="utf-8")
            self._run_seed(html_path=str(html_file))

        prop = Property.objects.get(tenant__slug=TENANT_SLUG, slug=PROPERTY_SLUG)
        self.assertEqual(prop.name, "Parsed Mango Name")
        self.assertEqual(prop.address, "99 Test ulica, Vodice")
        self.assertEqual(prop.branding["description"], "Parsed description text.")
