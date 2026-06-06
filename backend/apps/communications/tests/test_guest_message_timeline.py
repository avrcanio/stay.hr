from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.communications.guest_message_timeline import (
    timeline_for_reservation,
    whatsapp_display_body,
)
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class WhatsAppDisplayBodyTests(TestCase):
    def test_image_without_body(self):
        class Row:
            body = ""
            message_type = "image"

        self.assertEqual(whatsapp_display_body(Row()), "📷 Dokument poslan")

    def test_serialize_whatsapp_includes_media_url_for_intake_job(self):
        from apps.communications.guest_message_timeline import serialize_whatsapp
        from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobSource, DocumentIntakeJobStatus

        tenant = Tenant.objects.create(slug="media-test", name="Media Test")
        prop = Property.objects.create(tenant=tenant, name="P", slug="p")
        reservation = Reservation.objects.create(
            tenant=tenant,
            property=prop,
            booker_name="Guest",
            check_in=timezone.localdate(),
            check_out=timezone.localdate() + timedelta(days=1),
            status=Reservation.Status.EXPECTED,
        )
        integration = IntegrationConfig.objects.create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="123",
            is_active=True,
        )
        wa = WhatsAppMessage.objects.create(
            tenant_id=tenant.pk,
            integration=integration,
            reservation=reservation,
            wamid="wamid.media.test",
            wa_id="385991234567",
            direction=WhatsAppMessage.Direction.INBOUND,
            message_type="image",
            body="",
        )
        job = DocumentIntakeJob.objects.create(
            tenant_id=tenant.pk,
            reservation=reservation,
            whatsapp_message=wa,
            source=DocumentIntakeJobSource.WHATSAPP,
            status=DocumentIntakeJobStatus.DONE,
        )
        payload = serialize_whatsapp(wa)
        self.assertEqual(payload["document_intake_job_id"], job.pk)
        self.assertIn(f"/document-intake/jobs/{job.pk}/images/0/", payload["media_url"])
        self.assertEqual(payload["media_kind"], "image")

    def test_text_body_preserved(self):
        class Row:
            body = "Bok"
            message_type = "text"

        self.assertEqual(whatsapp_display_body(Row()), "Bok")


class TimelineDedupTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(tenant=self.tenant, name="Uzorita", slug="uzorita")
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key="1068791909660300",
            is_active=True,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booker_name="Ante Vrcan",
            booker_phone="+385976713511",
            check_in=timezone.localdate(),
            check_out=timezone.localdate() + timedelta(days=2),
            status=Reservation.Status.EXPECTED,
        )

    def test_whatsapp_api_outbound_deduped_against_guest_outbound(self):
        now = timezone.now()
        body = "Hvala vam na poslanim dokumentima!"
        draft = GuestMessageDraft.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            intent=GuestMessageIntent.REPLY,
            hint="checkin ready",
            llm_body_text=body,
            final_body_text=body,
            channel=GuestMessageChannel.WHATSAPP,
            sent_at=now,
        )
        GuestOutboundMessage.objects.create(
            tenant_id=self.tenant.pk,
            reservation=self.reservation,
            draft=draft,
            channel=GuestMessageChannel.WHATSAPP,
            body_text=body,
            status=GuestOutboundMessageStatus.SENT,
            to_phone=self.reservation.booker_phone,
            created_at=now,
        )
        WhatsAppMessage.objects.create(
            tenant_id=self.tenant.pk,
            integration=self.integration,
            reservation=self.reservation,
            wamid="wamid.outbound.dedup.test",
            wa_id="385976713511",
            phone_number_id="1068791909660300",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="text",
            body=body,
            created_at=now,
        )

        timeline = timeline_for_reservation(self.reservation)
        thank_you = [row for row in timeline if body in row["body_text"]]

        self.assertEqual(len(thank_you), 1)
        self.assertEqual(thank_you[0]["source"], "whatsapp")
        self.assertEqual(thank_you[0]["direction"], "outbound")
        self.assertEqual(thank_you[0]["status"], "sent")

    def test_whatsapp_handoff_kept_when_no_whatsapp_message_row(self):
        body = "Bok — check-in info"
        draft = GuestMessageDraft.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            intent=GuestMessageIntent.CHECKIN,
            llm_body_text=body,
            final_body_text=body,
            channel=GuestMessageChannel.WHATSAPP,
        )
        GuestOutboundMessage.objects.create(
            tenant_id=self.tenant.pk,
            reservation=self.reservation,
            draft=draft,
            channel=GuestMessageChannel.WHATSAPP,
            body_text=body,
            status=GuestOutboundMessageStatus.HANDOFF_WHATSAPP,
            to_phone=self.reservation.booker_phone,
            wa_me_url="https://wa.me/385976713511?text=hi",
        )

        timeline = timeline_for_reservation(self.reservation)
        handoff = [row for row in timeline if body in row["body_text"]]

        self.assertEqual(len(handoff), 1)
        self.assertEqual(handoff[0]["source"], "outbound")
        self.assertEqual(handoff[0]["status"], "handoff_whatsapp")
