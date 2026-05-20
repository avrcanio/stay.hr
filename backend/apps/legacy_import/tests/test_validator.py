from datetime import date

from django.test import TestCase, override_settings

from apps.integrations.models import IntegrationConfig
from apps.legacy_import.validator import UzoritaMigrationValidator
from apps.properties.models import Property
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant

# Validator unit tests assume legacy DB is unavailable (no UZORITA_DB_* in CI/test).
TEST_DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


@override_settings(DATABASES=TEST_DATABASES)
class ValidatorTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
            default_language="hr",
        )
        self.prop = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
        )

    def test_fails_without_data(self):
        report = UzoritaMigrationValidator(tenant_slug="uzorita").run()
        self.assertFalse(report.passed)

    def test_passes_with_matching_counts_and_config(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.prop,
            external_id="5307026805",
            check_in=date(2025, 7, 1),
            check_out=date(2025, 7, 5),
            status=Reservation.Status.EXPECTED,
            booker_name="Test Booker",
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            legacy_id=1,
            first_name="Ana",
            last_name="Anić",
            name="Ana Anić",
        )
        IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.EVISITOR,
            property=self.prop,
            is_active=True,
            config={"enabled": True},
        )

        report = UzoritaMigrationValidator(
            tenant_slug="uzorita",
            hash_sample_size=0,
        ).run()

        check_names = {c.name: c for c in report.checks}
        self.assertTrue(check_names["status_distribution"].passed)
        self.assertTrue(check_names["evisitor_config"].passed)
        self.assertTrue(check_names["reservation_count"].passed)
        self.assertTrue(check_names["guest_count"].passed)
        self.assertFalse(report.passed)
        self.assertFalse(check_names["hash_sample"].passed)
