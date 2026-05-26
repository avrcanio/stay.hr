from datetime import date

from django.test import TestCase

from apps.integrations.channex.booking_service import channex_external_id
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
