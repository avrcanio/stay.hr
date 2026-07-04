"""WhatsApp guest message send tests (Meta Cloud API)."""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.communications.models import GuestOutboundMessageStatus
from apps.integrations.tests.test_whatsapp_webhook import TEST_FERNET_KEY
from apps.integrations.whatsapp.client import WhatsAppApiError
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import RECEPTION_DEVICE_SCOPES, ApiApplication, Tenant


@override_settings(STAY_INTEGRATION_FERNET_KEY=TEST_FERNET_KEY)
@patch.dict("os.environ", {"WHATSAPP_ACCESS_TOKEN": "meta-test-token"}, clear=False)
class GuestMessageWhatsAppV2Tests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="V2 Tenant", slug="v2-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="V2 Property",
            slug="v2-property",
            address="Test 1",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R1",
            name="Room R1",
        )
        self.app, self.raw_token = ApiApplication.create_with_token(
            tenant=self.tenant,
            name="V2 tablet",
            scopes=RECEPTION_DEVICE_SCOPES,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="v2-res-1",
            booking_code="v2-res-1",
            check_in="2026-07-04",
            check_out="2026-07-05",
            booker_name="Ana Guest",
            booker_phone="+385981234567",
            amount=Decimal("100.00"),
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=self.unit,
            room_name="Room R1",
            sort_order=0,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Ana",
            last_name="Guest",
            is_primary=True,
        )
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}
        self.base = f"/api/v1/reception/reservations/{self.reservation.id}/messages"

    def _create_meta_integration(self):
        from apps.integrations.models import IntegrationConfig

        integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="1068791909660300",
            is_active=True,
        )
        integration.set_config_dict(
            {
                "phone_number_id": "1068791909660300",
                "waba_id": "123456789",
            }
        )
        integration.save()
        return integration

    def _compose_reply_draft(self) -> int:
        os.environ.pop("GUEST_COMPOSE_LLM_API_KEY", None)
        response = self.client.post(
            f"{self.base}/compose/",
            {"intent": "reply"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["draft_id"]

    @patch("apps.communications.guest_message_whatsapp_v2.send_text_message")
    def test_v2_send_text_when_session_open(self, mock_send):
        from apps.integrations.models import WhatsAppMessage

        mock_send.return_value = {"messages": [{"id": "wamid.v2.text.sent"}]}
        integration = self._create_meta_integration()
        WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=integration,
            reservation=self.reservation,
            wamid="wamid.in.v2.open",
            wa_id="385981234567",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="Hi",
            raw_payload={},
        )
        draft_id = self._compose_reply_draft()

        response = self.client.post(
            f"{self.base}/send/",
            {"draft_id": draft_id, "channel": "whatsapp", "body_text": "Reply in session"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["provider_message_id"], "wamid.v2.text.sent")
        mock_send.assert_called_once()

    @patch("apps.communications.guest_message_whatsapp_v2.send_text_message")
    def test_v2_reply_without_session_returns_template_required(self, mock_send):
        self._create_meta_integration()
        draft_id = self._compose_reply_draft()

        response = self.client.post(
            f"{self.base}/send/",
            {"draft_id": draft_id, "channel": "whatsapp", "body_text": "Outside session"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("whatsapp_template_required", response.content.decode())
        mock_send.assert_not_called()

    @patch("apps.communications.guest_message_whatsapp_v2.send_template_message")
    @patch("apps.communications.guest_message_whatsapp_v2.find_message_template")
    @patch("apps.communications.guest_message_whatsapp_v2.send_text_message")
    def test_v2_session_error_falls_back_to_template(self, mock_text, mock_find, mock_template):
        from apps.integrations.models import WhatsAppMessage

        mock_text.side_effect = WhatsAppApiError("WhatsApp API error 400: 131047 Re-engagement message")
        mock_find.return_value = {"status": "APPROVED", "name": "welcome_hr"}
        mock_template.return_value = {"messages": [{"id": "wamid.v2.template.sent"}]}
        integration = self._create_meta_integration()
        WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=integration,
            reservation=self.reservation,
            wamid="wamid.in.v2.stale",
            wa_id="385981234567",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="Old",
            raw_payload={},
        )

        compose = self.client.post(
            f"{self.base}/compose/",
            {"intent": "checkin"},
            format="json",
            **self.auth,
        )
        draft_id = compose.json()["draft_id"]

        response = self.client.post(
            f"{self.base}/send/",
            {"draft_id": draft_id, "channel": "whatsapp", "body_text": "Welcome"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["provider_message_id"], "wamid.v2.template.sent")
        mock_template.assert_called_once()
        mock_text.assert_called_once()

    @patch("apps.communications.guest_message_whatsapp_v2.send_text_message")
    def test_v2_transient_error_returns_pending_send(self, mock_send):
        from apps.integrations.models import WhatsAppMessage

        mock_send.side_effect = WhatsAppApiError("WhatsApp API error 503: Service unavailable")
        integration = self._create_meta_integration()
        WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=integration,
            reservation=self.reservation,
            wamid="wamid.in.v2.pending",
            wa_id="385981234567",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="Hi",
            raw_payload={},
        )
        draft_id = self._compose_reply_draft()

        response = self.client.post(
            f"{self.base}/send/",
            {"draft_id": draft_id, "channel": "whatsapp", "body_text": "Retry me"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 503, response.content)
        data = response.json()
        self.assertEqual(data["status"], "pending_send")

    @patch("apps.communications.guest_message_whatsapp_v2.send_text_message")
    def test_v2_idempotent_replay_after_sent(self, mock_send):
        from apps.communications.models import GuestMessageDraft
        from apps.integrations.models import WhatsAppMessage

        mock_send.return_value = {"messages": [{"id": "wamid.v2.idempotent"}]}
        integration = self._create_meta_integration()
        WhatsAppMessage.objects.create(
            tenant=self.tenant,
            integration=integration,
            reservation=self.reservation,
            wamid="wamid.in.v2.idem",
            wa_id="385981234567",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="text",
            body="Hi",
            raw_payload={},
        )
        draft_id = self._compose_reply_draft()

        first = self.client.post(
            f"{self.base}/send/",
            {"draft_id": draft_id, "channel": "whatsapp", "body_text": "Once"},
            format="json",
            **self.auth,
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(
            f"{self.base}/send/",
            {"draft_id": draft_id, "channel": "whatsapp", "body_text": "Once"},
            format="json",
            **self.auth,
        )
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()["status"], "sent")
        mock_send.assert_called_once()
        draft = GuestMessageDraft.objects.get(pk=draft_id)
        self.assertIsNotNone(draft.sent_at)

    def test_v2_no_integration_handoff_only(self):
        draft_id = self._compose_reply_draft()

        response = self.client.post(
            f"{self.base}/send/",
            {"draft_id": draft_id, "channel": "whatsapp", "body_text": "Handoff"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["status"], "handoff_whatsapp")
        self.assertEqual(data["handoff_reason"], "integration_not_configured")
