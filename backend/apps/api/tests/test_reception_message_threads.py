from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.communications.models import GuestMessageChannel, GuestOutboundMessage, GuestOutboundMessageStatus
from apps.integrations.models import ChannexMessage
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


class ReceptionMessageThreadsAPITests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Luxury Room Uzorita",
            slug="uzorita",
            timezone="Europe/Zagreb",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="Deluxe King Room R1",
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="Test tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5036489024",
            booking_code="5036489024",
            check_in=timezone.localdate(),
            check_out=timezone.localdate(),
            status=Reservation.Status.EXPECTED,
            booker_name="Daniela Heczko",
            booker_email="daniela@example.com",
            booker_phone="+385 91 1234567",
            amount=Decimal("180.15"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="Luxury Room Uzorita B&B",
            sort_order=0,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Daniela",
            last_name="Heczko",
            email="daniela@example.com",
            is_primary=True,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_list_threads_empty(self):
        response = self.client.get(
            "/api/v1/reception/message-threads/?sync=0",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["threads"], [])

    def test_list_threads_with_inbound_needs_reply(self):
        ChannexMessage.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            channex_booking_id="booking-1",
            channex_message_id="msg-in-1",
            direction=ChannexMessage.Direction.INBOUND,
            sender=ChannexMessage.Sender.GUEST,
            body="Hello from guest",
        )
        GuestOutboundMessage.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            channel=GuestMessageChannel.EMAIL,
            body_text="Earlier reply",
            status=GuestOutboundMessageStatus.SENT,
            created_at=timezone.now(),
        )
        ChannexMessage.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            channex_booking_id="booking-1",
            channex_message_id="msg-in-2",
            direction=ChannexMessage.Direction.INBOUND,
            sender=ChannexMessage.Sender.GUEST,
            body="Latest guest message",
        )

        response = self.client.get(
            "/api/v1/reception/message-threads/?sync=0",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["needs_reply_count"], 1)
        thread = data["threads"][0]
        self.assertEqual(thread["reservation_id"], self.reservation.pk)
        self.assertEqual(thread["booker_name"], "Daniela Heczko")
        self.assertEqual(thread["last_message_preview"], "Latest guest message")
        self.assertEqual(thread["last_channel"], "booking")
        self.assertEqual(thread["last_direction"], "inbound")
        self.assertTrue(thread["needs_reply"])
        self.assertTrue(thread["arrives_today"])

    def test_filter_needs_reply(self):
        other = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=timezone.localdate(),
            check_out=timezone.localdate(),
            status=Reservation.Status.EXPECTED,
            booker_name="Replied Guest",
        )
        ChannexMessage.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            channex_booking_id="b1",
            channex_message_id="m1",
            direction=ChannexMessage.Direction.INBOUND,
            sender=ChannexMessage.Sender.GUEST,
            body="Need reply",
        )
        GuestOutboundMessage.objects.create(
            tenant=self.tenant,
            reservation=other,
            channel=GuestMessageChannel.WHATSAPP,
            body_text="We replied",
            status=GuestOutboundMessageStatus.HANDOFF_WHATSAPP,
        )

        response = self.client.get(
            "/api/v1/reception/message-threads/?sync=0&needs_reply=1",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["threads"][0]["reservation_id"], self.reservation.pk)
