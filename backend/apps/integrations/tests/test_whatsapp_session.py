from django.test import TestCase
from django.utils import timezone

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.whatsapp_session import is_customer_service_window_open
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class WhatsAppSessionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Session Tenant", slug="session-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Session Property",
            slug="session-property",
            address="Test Address",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Guest",
            booker_phone="+385981234567",
            check_in=timezone.localdate(),
            check_out=timezone.localdate(),
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="123",
            is_active=True,
        )

    def test_session_closed_without_inbound(self):
        self.assertFalse(
            is_customer_service_window_open(
                tenant_id=self.tenant.pk,
                reservation=self.reservation,
            )
        )

    def test_session_open_after_inbound(self):
        WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.in.session.test",
            wa_id="385981234567",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="Hi",
        )
        self.assertTrue(
            is_customer_service_window_open(
                tenant_id=self.tenant.pk,
                reservation=self.reservation,
            )
        )
