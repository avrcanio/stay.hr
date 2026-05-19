from django.test import TestCase
from rest_framework.test import APIClient

from apps.tenants.models import PUBLIC_BOOKING_SCOPES, RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class FcmTokenRegisterTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        self.reception_app, self.reception_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Hospira tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.public_app, self.public_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Public widget",
            scopes=PUBLIC_BOOKING_SCOPES,
        )
        self.client = APIClient()

    def test_register_requires_auth(self):
        response = self.client.put(
            "/api/v1/app/fcm-token",
            {"token": "a" * 40},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_register_rejects_public_only_token(self):
        response = self.client.put(
            "/api/v1/app/fcm-token",
            {"token": "a" * 40},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.public_token}",
        )
        self.assertEqual(response.status_code, 403)

    def test_register_stores_token_on_application(self):
        fcm_token = "fcm-device-token-" + ("x" * 100)
        response = self.client.put(
            "/api/v1/app/fcm-token",
            {"token": fcm_token},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.reception_token}",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["registered"])
        self.assertEqual(data["application_id"], self.reception_app.pk)
        self.assertIn("fcm_token_updated_at", data)

        self.reception_app.refresh_from_db()
        self.assertEqual(self.reception_app.fcm_token, fcm_token)
        self.assertIsNotNone(self.reception_app.fcm_token_updated_at)

    def test_register_rejects_empty_token(self):
        response = self.client.put(
            "/api/v1/app/fcm-token",
            {"token": "   "},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.reception_token}",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_clears_token(self):
        self.reception_app.fcm_token = "existing-token-" + ("y" * 40)
        self.reception_app.save(update_fields=["fcm_token", "updated_at"])

        response = self.client.delete(
            "/api/v1/app/fcm-token",
            HTTP_AUTHORIZATION=f"Bearer {self.reception_token}",
        )
        self.assertEqual(response.status_code, 204)

        self.reception_app.refresh_from_db()
        self.assertEqual(self.reception_app.fcm_token, "")
        self.assertIsNone(self.reception_app.fcm_token_updated_at)
