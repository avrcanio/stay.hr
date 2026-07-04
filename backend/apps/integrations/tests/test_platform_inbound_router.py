from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.integrations.models import IntegrationConfig, WhatsAppInboundRouting, WhatsAppMessage
from apps.integrations.whatsapp.platform_inbound_router import route_inbound_message
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.constants import PLATFORM_TENANT_SLUG
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class PlatformInboundRouterTests(TestCase):
    def setUp(self):
        self.platform, _ = Tenant.objects.get_or_create(
            slug=PLATFORM_TENANT_SLUG,
            defaults={"name": "Platform", "is_system": True},
        )
        self.hotel = Tenant.objects.create(slug="uzorita-router", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.hotel,
            slug="uzorita",
            name="Uzorita",
        )
        self.integration, _ = IntegrationConfig.objects.update_or_create(
            tenant=self.platform,
            provider=IntegrationConfig.Provider.WHATSAPP,
            property=None,
            defaults={
                "routing_key": "1088787204326396",
                "is_active": True,
                "is_platform_default": True,
            },
        )
        self.integration.set_config_dict({"phone_number_id": "1088787204326396"})
        self.integration.save()
        self.reservation = Reservation.objects.create(
            tenant=self.hotel,
            property=self.property,
            booking_code="BCOM-42",
            booker_phone="+385976789626",
            booker_name="Ana",
            check_in=timezone.localdate(),
            check_out=timezone.localdate() + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
        )

    def _inbound(self, *, body: str = "", wa_id: str = "385976789626") -> WhatsAppMessage:
        return WhatsAppMessage.objects.create(
            tenant=self.platform,
            integration=self.integration,
            wamid=f"wamid.test.{wa_id}.{body[:8]}",
            wa_id=wa_id,
            phone_number_id="1088787204326396",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body=body,
        )

    def test_routes_by_booking_code_cross_tenant(self):
        msg = self._inbound(body="BCOM-42")
        routing = route_inbound_message(message=msg, integration=self.integration)
        self.assertEqual(routing.status, WhatsAppInboundRouting.Status.ROUTED)
        self.assertEqual(routing.routing_method, WhatsAppInboundRouting.RoutingMethod.BOOKING_CODE)
        self.assertEqual(routing.resolved_reservation_id, self.reservation.pk)
        msg.refresh_from_db()
        self.assertEqual(msg.reservation_id, self.reservation.pk)

    def test_routes_by_phone_cross_tenant(self):
        msg = self._inbound(body="Bok!")
        routing = route_inbound_message(message=msg, integration=self.integration)
        self.assertEqual(routing.status, WhatsAppInboundRouting.Status.ROUTED)
        self.assertEqual(routing.routing_method, WhatsAppInboundRouting.RoutingMethod.PHONE)

    def test_unrouted_when_no_match(self):
        msg = self._inbound(body="hello", wa_id="385911111111")
        routing = route_inbound_message(message=msg, integration=self.integration)
        self.assertEqual(routing.status, WhatsAppInboundRouting.Status.UNROUTED)

    def test_thread_routing_prefers_recent_outbound(self):
        WhatsAppMessage.objects.create(
            tenant=self.hotel,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.out.thread",
            wa_id="385976789626",
            phone_number_id="1088787204326396",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="text",
            body="Hi",
        )
        msg = self._inbound(body="reply")
        routing = route_inbound_message(message=msg, integration=self.integration)
        self.assertEqual(routing.routing_method, WhatsAppInboundRouting.RoutingMethod.THREAD)
        self.assertEqual(routing.resolved_reservation_id, self.reservation.pk)
