from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.core.notifications import send_tenant_reception_push, tenant_fcm_tokens
from apps.core.tasks import notify_new_reservation
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


@override_settings(FIREBASE_SERVICE_ACCOUNT_PATH="/run/secrets/firebase-service-account.json")
class TenantFcmTokensTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        self.app, _ = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )

    def test_returns_registered_tokens(self):
        self.app.fcm_token = "token-abc-" + ("x" * 40)
        self.app.save(update_fields=["fcm_token"])

        self.assertEqual(tenant_fcm_tokens(self.tenant.pk), [self.app.fcm_token])

    def test_ignores_empty_tokens(self):
        self.assertEqual(tenant_fcm_tokens(self.tenant.pk), [])


@override_settings(FIREBASE_SERVICE_ACCOUNT_PATH="/run/secrets/firebase-service-account.json")
class SendTenantReceptionPushTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        self.app, _ = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.app.fcm_token = "token-abc-" + ("x" * 40)
        self.app.save(update_fields=["fcm_token"])

    @patch("apps.core.notifications.send_fcm_message")
    def test_sends_to_all_tokens(self, mock_send):
        mock_send.return_value = "msg-1"
        ids = send_tenant_reception_push(
            tenant_id=self.tenant.pk,
            title="Nova rezervacija",
            body="Test",
            data={"event": "reservation_created"},
        )
        self.assertEqual(ids, ["msg-1"])
        mock_send.assert_called_once()


class NotifyNewReservationTaskTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Demo Property",
            slug="demo",
        )
        ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
            fcm_token="token-abc-" + ("x" * 40),
        )

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_builds_notification_payload(self, mock_push):
        mock_push.return_value = ["msg-1"]
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="TEST-001",
            check_in=date(2026, 5, 20),
            check_out=date(2026, 5, 22),
            status=Reservation.Status.EXPECTED,
            booker_name="Ana Anić",
            amount=Decimal("100.00"),
        )

        result = notify_new_reservation(reservation.pk)

        self.assertEqual(result["sent"], 1)
        mock_push.assert_called_once()
        kwargs = mock_push.call_args.kwargs
        self.assertEqual(kwargs["tenant_id"], self.tenant.pk)
        self.assertEqual(kwargs["title"], "Nova rezervacija")
        self.assertIn("Ana Anić", kwargs["body"])
        self.assertEqual(kwargs["data"]["event"], "reservation_created")
        self.assertEqual(kwargs["data"]["reservation_id"], str(reservation.pk))
