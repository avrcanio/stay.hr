from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.core.notifications import (
    reception_push_allowed,
    send_tenant_reception_push,
    tenant_fcm_tokens,
)
from apps.core.tasks import (
    notify_guest_message_inbound,
    notify_guest_review_inbound,
    notify_new_reservation,
    notify_reservation_status_changed,
)
from apps.integrations.models import ChannexReview, IntegrationConfig
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


@override_settings(
    FIREBASE_SERVICE_ACCOUNT_PATH="/run/secrets/firebase-service-account.json",
    FCM_PUSH_ENABLED=True,
    FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"],
)
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
            data={"type": "reservation.created"},
        )
        self.assertEqual(ids, ["msg-1"])
        mock_send.assert_called_once()


class ReceptionPushAllowedTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")

    @override_settings(FCM_PUSH_ENABLED=False, FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"])
    def test_push_disabled(self):
        decision = reception_push_allowed(tenant_id=self.tenant.pk)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.block_reason, "push_disabled")

    @override_settings(
        FCM_PUSH_ENABLED=True,
        FCM_PUSH_MAINTENANCE=True,
        FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"],
    )
    def test_maintenance_mode(self):
        decision = reception_push_allowed(tenant_id=self.tenant.pk)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.block_reason, "maintenance_mode")

    @override_settings(
        FCM_PUSH_ENABLED=False,
        FCM_PUSH_MAINTENANCE=True,
        FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"],
    )
    def test_push_disabled_precedes_maintenance(self):
        decision = reception_push_allowed(tenant_id=self.tenant.pk)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.block_reason, "push_disabled")

    @override_settings(FCM_PUSH_ENABLED=True, FCM_PUSH_ALLOWED_TENANT_SLUGS=[])
    def test_allowlist_empty(self):
        decision = reception_push_allowed(tenant_id=self.tenant.pk)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.block_reason, "allowlist_empty")
        self.assertEqual(decision.allowed_count, 0)

    @override_settings(FCM_PUSH_ENABLED=True, FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"])
    def test_slug_in_allowlist(self):
        decision = reception_push_allowed(tenant_id=self.tenant.pk)
        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.block_reason)
        self.assertEqual(decision.tenant_slug, "demo")
        self.assertEqual(decision.allowed_count, 1)

    @override_settings(FCM_PUSH_ENABLED=True, FCM_PUSH_ALLOWED_TENANT_SLUGS=["other"])
    def test_slug_not_in_allowlist(self):
        decision = reception_push_allowed(tenant_id=self.tenant.pk)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.block_reason, "tenant_not_allowed")
        self.assertEqual(decision.tenant_slug, "demo")
        self.assertEqual(decision.allowed_count, 1)

    @override_settings(FCM_PUSH_ENABLED=True, FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"])
    def test_tenant_not_found(self):
        decision = reception_push_allowed(tenant_id=999999)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.block_reason, "tenant_not_found")

    @override_settings(FCM_PUSH_ENABLED=True, FCM_PUSH_ALLOWED_TENANT_SLUGS=[" Demo ", "UZORITA"])
    def test_normalizes_allowlist_and_tenant_slug(self):
        decision = reception_push_allowed(tenant_id=self.tenant.pk)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.tenant_slug, "demo")
        self.assertEqual(decision.allowed_count, 2)


@override_settings(
    FIREBASE_SERVICE_ACCOUNT_PATH="/run/secrets/firebase-service-account.json",
    FCM_PUSH_ENABLED=True,
    FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"],
)
class SendTenantReceptionPushGuardTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Demo", slug="demo")
        self.app, _ = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.app.fcm_token = "token-abc-" + ("x" * 40)
        self.app.save(update_fields=["fcm_token"])

    @override_settings(FCM_PUSH_ENABLED=False, FCM_PUSH_ALLOWED_TENANT_SLUGS=["demo"])
    @patch("apps.core.notifications.send_fcm_message")
    def test_blocked_when_push_disabled(self, mock_send):
        ids = send_tenant_reception_push(
            tenant_id=self.tenant.pk,
            title="Test",
            body="Test",
        )
        self.assertEqual(ids, [])
        mock_send.assert_not_called()

    @override_settings(FCM_PUSH_MAINTENANCE=True)
    @patch("apps.core.notifications.send_fcm_message")
    def test_blocked_when_maintenance_mode(self, mock_send):
        ids = send_tenant_reception_push(
            tenant_id=self.tenant.pk,
            title="Test",
            body="Test",
        )
        self.assertEqual(ids, [])
        mock_send.assert_not_called()

    @override_settings(FCM_PUSH_ENABLED=True, FCM_PUSH_ALLOWED_TENANT_SLUGS=[])
    @patch("apps.core.notifications.send_fcm_message")
    def test_blocked_when_allowlist_empty(self, mock_send):
        ids = send_tenant_reception_push(
            tenant_id=self.tenant.pk,
            title="Test",
            body="Test",
        )
        self.assertEqual(ids, [])
        mock_send.assert_not_called()

    @override_settings(FCM_PUSH_ENABLED=True, FCM_PUSH_ALLOWED_TENANT_SLUGS=["other"])
    @patch("apps.core.notifications.send_fcm_message")
    def test_blocked_when_tenant_not_allowed(self, mock_send):
        ids = send_tenant_reception_push(
            tenant_id=self.tenant.pk,
            title="Test",
            body="Test",
        )
        self.assertEqual(ids, [])
        mock_send.assert_not_called()

    @patch("apps.core.notifications.send_fcm_message")
    def test_allowed_reaches_fcm(self, mock_send):
        mock_send.return_value = "msg-guard-1"
        ids = send_tenant_reception_push(
            tenant_id=self.tenant.pk,
            title="Nova rezervacija",
            body="Test",
            data={"type": "reservation.created"},
        )
        self.assertEqual(ids, ["msg-guard-1"])
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

    @patch("apps.core.tasks.notify_new_reservation.delay")
    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_builds_notification_payload(self, mock_push, mock_delay):
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
        mock_push.reset_mock()

        result = notify_new_reservation(reservation.pk)

        self.assertEqual(result["sent"], 1)
        mock_push.assert_called_once()
        kwargs = mock_push.call_args.kwargs
        self.assertEqual(kwargs["tenant_id"], self.tenant.pk)
        self.assertEqual(kwargs["title"], "Nova rezervacija")
        self.assertIn("Ana Anić", kwargs["body"])
        self.assertEqual(kwargs["data"]["type"], "reservation.created")
        self.assertEqual(kwargs["data"]["reservation_id"], str(reservation.pk))
        self.assertIn("Ana Anić", kwargs["data"]["summary"])


class NotifyReservationStatusChangedTaskTests(TestCase):
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
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="TEST-002",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.EXPECTED,
            booker_name="Marko Marković",
            amount=Decimal("200.00"),
        )

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_builds_status_changed_payload(self, mock_push):
        mock_push.return_value = ["msg-2"]
        result = notify_reservation_status_changed(
            self.reservation.pk,
            Reservation.Status.EXPECTED,
            Reservation.Status.CHECKED_IN,
            origin_installation_id="tablet-b-uuid",
        )
        self.assertEqual(result["sent"], 1)
        kwargs = mock_push.call_args.kwargs
        self.assertEqual(kwargs["data"]["type"], "reservation.status_changed")
        self.assertEqual(kwargs["data"]["reservation_id"], str(self.reservation.pk))
        self.assertEqual(kwargs["data"]["origin_installation_id"], "tablet-b-uuid")
        self.assertIn("expected", kwargs["data"]["summary"])
        self.assertIn("checked_in", kwargs["data"]["summary"])

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_skips_when_status_unchanged(self, mock_push):
        result = notify_reservation_status_changed(
            self.reservation.pk,
            Reservation.Status.EXPECTED,
            Reservation.Status.EXPECTED,
        )
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["reason"], "unchanged")
        mock_push.assert_not_called()


class NotifyGuestMessageInboundTaskTests(TestCase):
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
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="TEST-003",
            check_in=date(2026, 6, 10),
            check_out=date(2026, 6, 12),
            status=Reservation.Status.EXPECTED,
            booker_name="Petra Perić",
            amount=Decimal("150.00"),
        )

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_builds_booking_message_payload(self, mock_push):
        mock_push.return_value = ["msg-3"]
        result = notify_guest_message_inbound(
            self.reservation.pk,
            channel="booking",
            body_preview="Dobro jutro, imamo pitanje o parkingu.",
        )
        self.assertEqual(result["sent"], 1)
        kwargs = mock_push.call_args.kwargs
        self.assertEqual(kwargs["title"], "Nova poruka")
        self.assertIn("Petra Perić", kwargs["body"])
        self.assertIn("Booking.com", kwargs["body"])
        self.assertIn("parking", kwargs["body"])
        self.assertEqual(kwargs["data"]["type"], "guest.message.received")
        self.assertEqual(kwargs["data"]["reservation_id"], str(self.reservation.pk))
        self.assertEqual(kwargs["data"]["channel"], "booking")

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_builds_whatsapp_fallback_preview(self, mock_push):
        mock_push.return_value = ["msg-4"]
        result = notify_guest_message_inbound(
            self.reservation.pk,
            channel="whatsapp",
            body_preview="",
        )
        self.assertEqual(result["sent"], 1)
        kwargs = mock_push.call_args.kwargs
        self.assertIn("WhatsApp", kwargs["body"])
        self.assertEqual(kwargs["data"]["channel"], "whatsapp")

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_skips_empty_booking_preview(self, mock_push):
        result = notify_guest_message_inbound(
            self.reservation.pk,
            channel="booking",
            body_preview="   ",
        )
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["reason"], "empty_preview")
        mock_push.assert_not_called()


class NotifyGuestReviewInboundTaskTests(TestCase):
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
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="5307026805",
            check_in=date(2026, 6, 10),
            check_out=date(2026, 6, 12),
            status=Reservation.Status.EXPECTED,
            booker_name="Joan March",
            amount=Decimal("150.00"),
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.review = ChannexReview.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            channex_review_id="review-uuid-push",
            ota="BookingCom",
            content="Excellent stay",
            overall_score=Decimal("9.5"),
            is_replied=False,
        )

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_builds_review_received_payload(self, mock_push):
        mock_push.return_value = ["msg-review-1"]
        result = notify_guest_review_inbound(
            self.reservation.pk,
            review_id=self.review.pk,
            ota="BookingCom",
            score_preview="9.5",
            content_preview="Excellent stay",
        )
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["review_id"], self.review.pk)
        kwargs = mock_push.call_args.kwargs
        self.assertEqual(kwargs["title"], "Nova recenzija")
        self.assertIn("Joan March", kwargs["body"])
        self.assertIn("BookingCom", kwargs["body"])
        self.assertIn("Excellent stay", kwargs["body"])
        self.assertEqual(kwargs["data"]["type"], "guest.review.received")
        self.assertEqual(kwargs["data"]["reservation_id"], str(self.reservation.pk))
        self.assertEqual(kwargs["data"]["review_id"], str(self.review.pk))
        self.assertEqual(kwargs["data"]["booking_code"], "5307026805")

    @patch("apps.core.notifications.send_tenant_reception_push")
    def test_skips_when_reservation_missing(self, mock_push):
        result = notify_guest_review_inbound(
            999999,
            review_id=self.review.pk,
            ota="BookingCom",
            content_preview="Missing reservation",
        )
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["reason"], "not_found")
        mock_push.assert_not_called()
