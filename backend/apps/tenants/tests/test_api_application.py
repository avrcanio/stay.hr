from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.tenants.models import (
    RECEPTION_DEVICE_SCOPES,
    VALID_SCOPES,
    ApiApplication,
    Tenant,
)


class ApiApplicationScopeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")

    def test_reception_scopes_are_valid(self):
        self.assertTrue(set(RECEPTION_DEVICE_SCOPES).issubset(VALID_SCOPES))

    def test_create_with_reception_scopes(self):
        app, raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Hospira tablet 1",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.assertTrue(raw_token.startswith("stay_pk_live_"))
        self.assertEqual(set(app.scopes), set(RECEPTION_DEVICE_SCOPES))
        self.assertTrue(app.is_active)

    def test_rejects_unknown_scope(self):
        app = ApiApplication(
            tenant=self.tenant,
            name="Bad app",
            scopes=["reception:read", "super:admin"],
        )
        with self.assertRaises(ValidationError):
            app.full_clean()
