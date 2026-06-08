from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations.channex.booking_service import channex_external_id
from apps.integrations.channex.message_service import (
    relink_unlinked_channex_messages,
    resolve_reservation_for_channex_message,
    sync_booking_messages_from_channex,
)
from apps.integrations.channex.webhook_service import record_channex_webhook
from apps.integrations.models import ChannexMessage, IntegrationConfig
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import ChannelManager, Tenant, TenantReceptionSettings


class ChannexMessageWebhookTests(TestCase):
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
        self.payload = {
            "id": "msg-uuid-789",
            "message": "Hello from guest",
            "sender": "guest",
            "booking_id": self.booking_id,
            "message_thread_id": "thread-uuid-001",
            "ota_message_id": "ota-msg-001",
            "attachments": [],
            "have_attachment": False,
        }

    def test_message_webhook_creates_inbound_row(self):
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="message",
            property_id="prop-uuid-123",
            body={"payload": self.payload},
        )

        row = ChannexMessage.objects.get(channex_message_id="msg-uuid-789")
        self.assertEqual(row.direction, ChannexMessage.Direction.INBOUND)
        self.assertEqual(row.sender, ChannexMessage.Sender.GUEST)
        self.assertEqual(row.body, "Hello from guest")
        self.assertEqual(row.reservation_id, self.reservation.id)
        self.assertEqual(row.channex_booking_id, self.booking_id)

    def test_message_webhook_is_idempotent(self):
        body = {"payload": self.payload}
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="message",
            property_id="prop-uuid-123",
            body=body,
        )
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="message",
            property_id="prop-uuid-123",
            body=body,
        )
        self.assertEqual(ChannexMessage.objects.count(), 1)

    def test_message_webhook_links_legacy_booking_code_external_id(self):
        legacy = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5856279283",
            booking_code="5856279283",
            import_source="channex",
            check_in=date(2026, 6, 7),
            check_out=date(2026, 6, 8),
            booker_name="Markus Zöhrer",
            status=Reservation.Status.EXPECTED,
        )
        payload = {
            **self.payload,
            "id": "msg-legacy-link",
            "booking_id": "unknown-channex-booking-uuid",
            "ota_reservation_code": "5856279283",
            "message": "Frühstück morgen?",
        }
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="message",
            property_id="prop-uuid-123",
            body={"payload": payload},
        )
        row = ChannexMessage.objects.get(channex_message_id="msg-legacy-link")
        self.assertEqual(row.reservation_id, legacy.id)

    def test_relink_unlinked_messages_by_booking_code(self):
        legacy = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="6756930554",
            booking_code="6756930554",
            import_source="channex",
            check_in=date(2026, 6, 7),
            check_out=date(2026, 6, 8),
            booker_name="Audrius Kavaliauskas",
            status=Reservation.Status.EXPECTED,
        )
        ChannexMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=None,
            channex_booking_id="other-booking-uuid",
            channex_message_id="orphan-msg-1",
            direction=ChannexMessage.Direction.INBOUND,
            sender=ChannexMessage.Sender.GUEST,
            body="Test orphan",
            raw_payload={"ota_reservation_code": "6756930554"},
        )
        updated = relink_unlinked_channex_messages(self.tenant)
        self.assertEqual(updated, 1)
        row = ChannexMessage.objects.get(channex_message_id="orphan-msg-1")
        self.assertEqual(row.reservation_id, legacy.id)

    def test_resolve_reservation_for_message_by_booking_code(self):
        legacy = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="999888777",
            booking_code="999888777",
            import_source="channex",
            check_in=date(2026, 6, 7),
            check_out=date(2026, 6, 8),
            booker_name="Legacy Guest",
            status=Reservation.Status.EXPECTED,
        )
        resolved = resolve_reservation_for_channex_message(
            self.tenant,
            booking_id="unknown-channex-uuid",
            ota_reservation_id="999888777",
        )
        self.assertEqual(resolved.pk, legacy.id)

    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    @patch("apps.integrations.channex.message_service.ChannexClient")
    def test_sync_booking_messages_notifies_new_guest_message(
        self, mock_client_cls, mock_notify
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.list_booking_messages.return_value = {
            "data": [
                {
                    "id": "msg-sync-notify-1",
                    "message": "Late guest reply via API pull",
                    "sender": "guest",
                    "booking_id": self.booking_id,
                }
            ]
        }

        rows = sync_booking_messages_from_channex(self.integration, self.reservation)
        self.assertEqual(len(rows), 1)
        mock_notify.assert_called_once_with(
            self.reservation.pk,
            channel="booking",
            body_preview="Late guest reply via API pull",
        )

    @patch("apps.core.tasks.notify_guest_message_inbound.delay")
    @patch("apps.integrations.channex.message_service.ChannexClient")
    def test_sync_booking_messages_skips_notify_when_already_stored(
        self, mock_client_cls, mock_notify
    ):
        record_channex_webhook(
            integration_row=self.integration,
            tenant=self.tenant,
            event="message",
            property_id="prop-uuid-123",
            body={"payload": self.payload},
        )
        mock_notify.reset_mock()

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.list_booking_messages.return_value = {
            "data": [
                {
                    "id": "msg-uuid-789",
                    "message": "Hello from guest",
                    "sender": "guest",
                    "booking_id": self.booking_id,
                }
            ]
        }

        sync_booking_messages_from_channex(self.integration, self.reservation)
        mock_notify.assert_not_called()
