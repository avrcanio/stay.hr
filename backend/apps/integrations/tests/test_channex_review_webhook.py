from datetime import date
from decimal import Decimal

from unittest.mock import patch

from django.test import TestCase

from apps.integrations.channex.booking_service import channex_external_id
from apps.integrations.channex.webhook_service import record_channex_webhook
from apps.integrations.models import ChannexReview, IntegrationConfig
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class ChannexReviewWebhookTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="uzorita",
            name="Uzorita",
            timezone="Europe/Zagreb",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "property_id": "prop-uuid-123",
                "sync_property_slug": "uzorita",
            }
        )
        self.integration.save()
        self.booking_id = "booking-uuid-456"
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id=channex_external_id(self.booking_id),
            import_source="channex",
            check_in=date(2026, 6, 20),
            check_out=date(2026, 6, 21),
            booker_name="Veble Vesna",
            status=Reservation.Status.EXPECTED,
        )
        self.review_id = "review-uuid-789"
        self.payload = {
            "id": self.review_id,
            "content": None,
            "reply": None,
            "booking_id": self.booking_id,
            "ota": "BookingCom",
            "ota_reservation_id": "4874110092",
            "overall_score": 10.0,
            "scores": [{"category": "clean", "score": 10.0}],
            "is_replied": False,
            "is_hidden": False,
            "received_at": "2026-06-05T07:35:21.000000",
            "expired_at": "2026-11-03T07:35:21.000000",
        }

    def test_review_webhook_creates_row(self):
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="review",
            property_id="prop-uuid-123",
            body={"payload": self.payload},
        )

        row = ChannexReview.objects.get(channex_review_id=self.review_id)
        self.assertEqual(row.reservation_id, self.reservation.id)
        self.assertEqual(row.ota, "BookingCom")
        self.assertEqual(row.overall_score, Decimal("10.0"))
        self.assertFalse(row.is_replied)

    @patch("apps.core.tasks.notify_guest_review_inbound.delay")
    def test_review_webhook_queues_push(self, mock_notify_delay):
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="review",
            property_id="prop-uuid-123",
            body={"payload": self.payload},
        )

        row = ChannexReview.objects.get(channex_review_id=self.review_id)
        mock_notify_delay.assert_called_once_with(
            self.reservation.id,
            review_id=row.pk,
            ota="BookingCom",
            score_preview="10.0",
            content_preview="",
        )

    @patch("apps.core.tasks.notify_guest_review_inbound.delay")
    def test_updated_review_with_content_queues_push(self, mock_notify_delay):
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="review",
            property_id="prop-uuid-123",
            body={"payload": self.payload},
        )
        mock_notify_delay.reset_mock()

        updated = {
            **self.payload,
            "content": "Great stay, thank you!",
        }
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="updated_review",
            property_id="prop-uuid-123",
            body={"payload": updated},
        )

        row = ChannexReview.objects.get(channex_review_id=self.review_id)
        mock_notify_delay.assert_called_once_with(
            self.reservation.id,
            review_id=row.pk,
            ota="BookingCom",
            score_preview="10.0",
            content_preview="Great stay, thank you!",
        )

    @patch("apps.core.tasks.notify_guest_review_inbound.delay")
    def test_unlinked_review_skips_push(self, mock_notify_delay):
        unlinked_payload = {
            **self.payload,
            "booking_id": "unknown-booking",
            "ota_reservation_id": "9999999999",
        }
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="review",
            property_id="prop-uuid-123",
            body={"payload": unlinked_payload},
        )

        self.assertTrue(ChannexReview.objects.filter(channex_review_id=self.review_id).exists())
        mock_notify_delay.assert_not_called()

    def test_updated_review_updates_content(self):
        body = {"payload": self.payload}
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="review",
            property_id="prop-uuid-123",
            body=body,
        )
        updated = {
            **self.payload,
            "content": "Great stay, thank you!",
        }
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="updated_review",
            property_id="prop-uuid-123",
            body={"payload": updated},
        )
        self.assertEqual(ChannexReview.objects.count(), 1)
        row = ChannexReview.objects.get(channex_review_id=self.review_id)
        self.assertEqual(row.content, "Great stay, thank you!")

    def test_updated_review_normalizes_dict_reply(self):
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="review",
            property_id="prop-uuid-123",
            body={"payload": self.payload},
        )

        updated = {
            **self.payload,
            "reply": {"reply": "Hvala vam na ocjeni"},
            "is_replied": False,
        }
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="updated_review",
            property_id="prop-uuid-123",
            body={"payload": updated},
        )

        row = ChannexReview.objects.get(channex_review_id=self.review_id)
        self.assertEqual(row.reply, "Hvala vam na ocjeni")
        self.assertTrue(row.is_replied)
