from cryptography.fernet import Fernet
from django.test import TestCase, override_settings

from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant
from apps.tenants.token_encryption import (
    ApiTokenEncryptionError,
    decrypt_api_token,
    encrypt_api_token,
)

TEST_FERNET_KEY = Fernet.generate_key().decode()


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class ApiTokenEncryptionTests(TestCase):
    def test_roundtrip(self):
        raw = "stay_pk_live_test_roundtrip_token"
        ciphertext = encrypt_api_token(raw)
        self.assertNotEqual(ciphertext, raw)
        self.assertEqual(decrypt_api_token(ciphertext), raw)

    def test_empty_ciphertext(self):
        self.assertEqual(decrypt_api_token(""), "")


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class ApiApplicationStoredTokenTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")

    def test_create_with_token_stores_encrypted(self):
        app, raw = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Hospira tablet 1",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.assertTrue(app.token_encrypted)
        self.assertEqual(app.get_stored_token(), raw)

    def test_regenerate_changes_hash_and_stored_token(self):
        app, first_raw = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Hospira tablet 1",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        first_hash = app.public_key_hash
        second_raw = app.regenerate_token()
        app.refresh_from_db()

        self.assertNotEqual(second_raw, first_raw)
        self.assertNotEqual(app.public_key_hash, first_hash)
        self.assertEqual(app.get_stored_token(), second_raw)

    def test_missing_encrypted_returns_none(self):
        app = ApiApplication.objects.create(
            tenant=self.tenant,
            name="Legacy",
            scopes=RECEPTION_DEVICE_SCOPES,
            public_key_hash="a" * 64,
            token_encrypted="",
        )
        self.assertIsNone(app.get_stored_token())


@override_settings(STAY_INTEGRATION_FERNET_KEY="")
class ApiTokenEncryptionMissingKeyTests(TestCase):
    def test_encrypt_requires_key(self):
        with self.assertRaises(ApiTokenEncryptionError):
            encrypt_api_token("stay_pk_live_x")
