from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.integrations.models import IntegrationConfig, WhatsAppInboundRouting, WhatsAppMessage
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.constants import PLATFORM_TENANT_SLUG
from apps.tenants.models import Tenant

TEST_FERNET_KEY = "M8U_DJpQILQrKpxTOVtRrQp3nR0LJHAl2X0x-7JOH5k="


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
class PlatformWhatsAppUnroutedApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser("su", "su@test.com", "pass")
        self.user = User.objects.create_user("staff", "staff@test.com", "pass")
        self.client = APIClient()

        self.platform, _ = Tenant.objects.get_or_create(
            slug=PLATFORM_TENANT_SLUG,
            defaults={"name": "Platform", "is_system": True},
        )
        self.hotel = Tenant.objects.create(slug="uzorita-unrouted", name="Uzorita")
        self.property = Property.objects.create(
            tenant=self.hotel,
            slug="uzorita",
            name="Uzorita",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.hotel,
            property=self.property,
            booking_code="X1",
            booker_phone="+385976789626",
            check_in="2026-07-01",
            check_out="2026-07-03",
            status=Reservation.Status.EXPECTED,
        )
        integration = IntegrationConfig.objects.create(
            tenant=self.platform,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="pnid",
            is_active=True,
            is_platform_default=True,
        )
        msg = WhatsAppMessage.objects.create(
            tenant=self.platform,
            integration=integration,
            wamid="wamid.unrouted.1",
            wa_id="385911111111",
            phone_number_id="pnid",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="help",
        )
        self.routing = WhatsAppInboundRouting.objects.create(
            tenant=self.platform,
            message=msg,
            status=WhatsAppInboundRouting.Status.UNROUTED,
        )

    def test_list_requires_superuser(self):
        self.client.force_authenticate(self.user)
        url = reverse("platform-whatsapp-unrouted")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_list_unrouted_superuser(self):
        self.client.force_authenticate(self.superuser)
        url = reverse("platform-whatsapp-unrouted")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["items"][0]["id"], self.routing.pk)

    def test_link_unrouted_message(self):
        self.client.force_authenticate(self.superuser)
        url = reverse("platform-whatsapp-unrouted-action", kwargs={"routing_id": self.routing.pk})
        response = self.client.post(
            url,
            {"action": "link", "reservation_id": self.reservation.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.routing.refresh_from_db()
        self.assertEqual(self.routing.status, WhatsAppInboundRouting.Status.ROUTED)
        self.assertEqual(self.routing.resolved_reservation_id, self.reservation.pk)

    def test_dismiss_unrouted_message(self):
        self.client.force_authenticate(self.superuser)
        url = reverse("platform-whatsapp-unrouted-action", kwargs={"routing_id": self.routing.pk})
        response = self.client.post(url, {"action": "dismiss"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.routing.refresh_from_db()
        self.assertEqual(self.routing.status, WhatsAppInboundRouting.Status.DISMISSED)
