"""PR-C: guest portal link distribution after web check-in."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.communications.guest_compose import (
    HINT_GUEST_PORTAL_LINK,
    HINT_GUEST_PORTAL_LINK_URL,
    render_guest_portal_link_email_html,
    render_guest_portal_link_message,
    render_guest_portal_link_url_only,
)
from apps.communications.guest_portal_distribute import (
    portal_link_already_sent,
    resolve_portal_link_channel,
    send_guest_portal_link_for_session,
)
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessageStatus,
)
from apps.properties.models import Property
from apps.reservations.guest_checkin_orchestrator import GuestCheckInOrchestrator
from apps.reservations.guest_checkin_session import ensure_active_session, mark_session_completed
from apps.reservations.models import (
    Guest,
    GuestCheckInSessionCreatedFrom,
    GuestCheckInSessionStatus,
    GuestPortalAccess,
    Reservation,
)
from apps.tenants.models import Tenant


class ResolvePortalLinkChannelTests(TestCase):
    def test_channel_map(self):
        self.assertEqual(
            resolve_portal_link_channel(GuestCheckInSessionCreatedFrom.CHANNEX),
            GuestMessageChannel.BOOKING,
        )
        self.assertEqual(
            resolve_portal_link_channel(GuestCheckInSessionCreatedFrom.EMAIL),
            GuestMessageChannel.EMAIL,
        )
        self.assertEqual(
            resolve_portal_link_channel(GuestCheckInSessionCreatedFrom.WHATSAPP_AUTOCHECKIN),
            GuestMessageChannel.WHATSAPP,
        )
        self.assertEqual(
            resolve_portal_link_channel(GuestCheckInSessionCreatedFrom.RECEPTION_MANUAL),
            GuestMessageChannel.EMAIL,
        )
        self.assertIsNone(resolve_portal_link_channel("unknown"))


class GuestPortalComposeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="gp-compose", name="GP Compose")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Compose Property",
            slug="compose",
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="GP-C-1",
            check_in=date(2026, 7, 21),
            check_out=date(2026, 7, 23),
            booker_name="Ada",
            booker_country="GB",
            status=Reservation.Status.EXPECTED,
        )

    def test_cta_message_has_no_portal_url(self):
        url = "https://booking.example.test/g/tok"
        text = render_guest_portal_link_message(self.reservation, portal_url=url)
        self.assertNotIn(url, text)
        self.assertNotIn("/g/tok", text)
        self.assertNotIn("booking.example", text)
        self.assertIn("arrival", text.lower())
        # Footer stay.hr link is fine; portal URL must not appear.
        self.assertIn("stay.hr", text)

    def test_url_only_is_localized_link(self):
        url = "https://booking.example.test/g/tok"
        text = render_guest_portal_link_url_only(self.reservation, portal_url=url)
        self.assertTrue(text.startswith(url))
        self.assertIn("?lang=", text)
        self.assertEqual(text.strip(), text)
        self.assertNotIn("\n", text)

    def test_email_html_has_button_plain_cta_without_url(self):
        url = "https://booking.example.test/g/tok"
        html = render_guest_portal_link_email_html(self.reservation, portal_url=url)
        self.assertIn("href=", html)
        self.assertIn(url, html)
        # Plain CTA paragraph must not embed the portal URL as text.
        plain_p = html.split("<p>")[1].split("</p>")[0]
        self.assertNotIn("http", plain_p.lower())
        self.assertIn("arrival", plain_p.lower())


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class GuestPortalDistributeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="gp-dist", name="GP Dist")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Dist Property",
            slug="dist",
            guest_checkin_opens_days_before=7,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="GP-D-1",
            check_in=date(2026, 7, 21),
            check_out=date(2026, 7, 24),
            adults_count=1,
            booker_name="Portal Guest",
            booker_email="guest@example.com",
            booker_phone="+385911111111",
            amount=Decimal("90.00"),
            status=Reservation.Status.EXPECTED,
            import_source="channex",
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Portal",
            last_name="Guest",
            name="Portal Guest",
            is_primary=True,
        )

    def _complete_session(self, created_from: str):
        session = ensure_active_session(self.reservation, created_from=created_from)
        mark_session_completed(session)
        session.refresh_from_db()
        return session

    def test_email_channel_uses_email_not_whatsapp(self):
        session = self._complete_session(GuestCheckInSessionCreatedFrom.EMAIL)
        sent_channels: list[str] = []

        def fake_email(*args, **kwargs):
            draft = kwargs.get("draft")
            if draft is not None:
                draft.channel = GuestMessageChannel.EMAIL
                draft.final_body_text = args[1] if len(args) > 1 else ""
                draft.save(update_fields=["channel", "final_body_text"])
            outbound = MagicMock()
            outbound.status = GuestOutboundMessageStatus.SENT
            sent_channels.append(GuestMessageChannel.EMAIL)
            return outbound

        with (
            patch(
                "apps.communications.guest_portal_distribute.send_guest_email_with_timeline_record",
                side_effect=fake_email,
            ) as mock_email,
            patch(
                "apps.communications.guest_portal_distribute.send_guest_message",
            ) as mock_send,
        ):
            result = send_guest_portal_link_for_session(
                reservation_id=self.reservation.pk,
                session_id=session.pk,
            )

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["channel"], GuestMessageChannel.EMAIL)
        mock_email.assert_called_once()
        mock_send.assert_not_called()
        self.assertEqual(sent_channels, [GuestMessageChannel.EMAIL])
        self.assertTrue(
            GuestMessageDraft.objects.filter(
                reservation=self.reservation,
                hint=HINT_GUEST_PORTAL_LINK,
            ).exists()
        )
        self.assertTrue(
            GuestPortalAccess.objects.filter(reservation=self.reservation).exists()
        )

    def test_channex_uses_booking_two_sends(self):
        session = self._complete_session(GuestCheckInSessionCreatedFrom.CHANNEX)
        bodies: list[str] = []

        def fake_send(*, channel, **kwargs):
            draft = kwargs["draft"]
            draft.channel = channel
            draft.final_body_text = kwargs["body_text"]
            bodies.append(kwargs["body_text"])
            from django.utils import timezone

            draft.sent_at = timezone.now()
            draft.save(update_fields=["channel", "final_body_text", "sent_at"])
            return MagicMock(delivery_status="sent")

        with (
            patch(
                "apps.communications.guest_portal_distribute.send_guest_message",
                side_effect=fake_send,
            ) as mock_send,
            patch(
                "apps.communications.guest_portal_distribute.send_guest_email_with_timeline_record",
            ) as mock_email,
        ):
            result = send_guest_portal_link_for_session(
                reservation_id=self.reservation.pk,
                session_id=session.pk,
            )

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["channel"], GuestMessageChannel.BOOKING)
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(
            mock_send.call_args_list[0].kwargs["channel"],
            GuestMessageChannel.BOOKING,
        )
        self.assertEqual(
            mock_send.call_args_list[1].kwargs["channel"],
            GuestMessageChannel.BOOKING,
        )
        mock_email.assert_not_called()
        self.assertNotIn("/g/", bodies[0])
        self.assertTrue(bodies[1].startswith("http"))
        self.assertIn("?lang=", bodies[1])
        self.assertTrue(
            GuestMessageDraft.objects.filter(
                reservation=self.reservation,
                hint=HINT_GUEST_PORTAL_LINK,
            ).exists()
        )
        self.assertTrue(
            GuestMessageDraft.objects.filter(
                reservation=self.reservation,
                hint=HINT_GUEST_PORTAL_LINK_URL,
            ).exists()
        )
        self.assertIn("url_draft_id", result)

    def test_whatsapp_autocheckin_uses_whatsapp_two_sends(self):
        session = self._complete_session(
            GuestCheckInSessionCreatedFrom.WHATSAPP_AUTOCHECKIN,
        )
        bodies: list[str] = []

        def fake_send(*, channel, **kwargs):
            draft = kwargs["draft"]
            draft.channel = channel
            draft.final_body_text = kwargs["body_text"]
            bodies.append(kwargs["body_text"])
            from django.utils import timezone

            draft.sent_at = timezone.now()
            draft.save(update_fields=["channel", "final_body_text", "sent_at"])
            outbound = MagicMock()
            outbound.status = GuestOutboundMessageStatus.SENT
            return outbound

        with patch(
            "apps.communications.guest_portal_distribute.send_guest_message",
            side_effect=fake_send,
        ) as mock_send:
            result = send_guest_portal_link_for_session(
                reservation_id=self.reservation.pk,
                session_id=session.pk,
            )

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["channel"], GuestMessageChannel.WHATSAPP)
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(
            mock_send.call_args_list[0].kwargs["channel"],
            GuestMessageChannel.WHATSAPP,
        )
        self.assertEqual(
            mock_send.call_args_list[1].kwargs["channel"],
            GuestMessageChannel.WHATSAPP,
        )
        self.assertNotIn("/g/", bodies[0])
        self.assertTrue(bodies[1].startswith("http"))

    def test_channex_partial_when_url_send_fails(self):
        session = self._complete_session(GuestCheckInSessionCreatedFrom.CHANNEX)
        calls = {"n": 0}

        def fake_send(*, channel, **kwargs):
            calls["n"] += 1
            draft = kwargs["draft"]
            draft.channel = channel
            draft.final_body_text = kwargs["body_text"]
            from django.utils import timezone

            draft.sent_at = timezone.now()
            draft.save(update_fields=["channel", "final_body_text", "sent_at"])
            if calls["n"] == 2:
                raise RuntimeError("url send boom")
            return MagicMock(delivery_status="sent")

        with patch(
            "apps.communications.guest_portal_distribute.send_guest_message",
            side_effect=fake_send,
        ):
            result = send_guest_portal_link_for_session(
                reservation_id=self.reservation.pk,
                session_id=session.pk,
            )

        self.assertEqual(result["status"], "partial")
        self.assertIn("draft_id", result)
        self.assertIn("url_draft_id", result)
        self.assertIn("url send boom", result["error"])
        # Dedup hint still present so retries do not double-send CTA.
        self.assertTrue(portal_link_already_sent(self.reservation))

    def test_reception_manual_without_email_skips(self):
        self.reservation.booker_email = ""
        self.reservation.save(update_fields=["booker_email", "updated_at"])
        session = self._complete_session(
            GuestCheckInSessionCreatedFrom.RECEPTION_MANUAL,
        )
        result = send_guest_portal_link_for_session(
            reservation_id=self.reservation.pk,
            session_id=session.pk,
        )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "no_email")
        self.assertFalse(portal_link_already_sent(self.reservation))

    def test_dedup_hint_once_per_reservation(self):
        session = self._complete_session(GuestCheckInSessionCreatedFrom.EMAIL)
        GuestMessageDraft.objects.create(
            tenant_id=self.tenant.pk,
            reservation=self.reservation,
            intent=GuestMessageIntent.CHECKIN,
            hint=HINT_GUEST_PORTAL_LINK,
            llm_body_text="already",
            final_body_text="already",
            language="en",
            channel=GuestMessageChannel.EMAIL,
        )
        with patch(
            "apps.communications.guest_portal_distribute.send_guest_email_with_timeline_record",
        ) as mock_email:
            result = send_guest_portal_link_for_session(
                reservation_id=self.reservation.pk,
                session_id=session.pk,
            )
        self.assertEqual(result["status"], "already_sent")
        mock_email.assert_not_called()


class CompleteSessionEnqueuesPortalLinkTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="gp-enq", name="GP Enq")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Enq Property",
            slug="enq",
            guest_checkin_opens_days_before=7,
        )
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="GP-E-1",
            check_in=date(2026, 7, 25),
            check_out=date(2026, 7, 28),
            adults_count=1,
            booker_name="Enqueue Guest",
            booker_email="enq@example.com",
            amount=Decimal("50.00"),
            status=Reservation.Status.EXPECTED,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            first_name="Enq",
            last_name="Guest",
            name="Enq Guest",
            is_primary=True,
            date_of_birth=date(1990, 1, 1),
            nationality="HR",
            sex="female",
            document_number="11223344",
            document_type="identity_card",
            address="Zadar",
        )

    @patch(
        "apps.reservations.guest_checkin_tasks.send_guest_portal_link_after_checkin.delay",
    )
    def test_complete_session_enqueues_task_on_commit(self, mock_delay):
        ensured = GuestCheckInOrchestrator.ensure_session_and_link(
            self.reservation,
            created_from=GuestCheckInSessionCreatedFrom.EMAIL,
        )
        GuestCheckInOrchestrator.patch_slot(
            ensured.session,
            self.reservation,
            position=1,
            fields={
                "first_name": "Enq",
                "last_name": "Guest",
                "date_of_birth": "1990-01-01",
                "nationality": "HR",
                "sex": "female",
                "document_number": "11223344",
                "document_type": "identity_card",
                "address": "Zadar",
            },
        )

        with self.captureOnCommitCallbacks(execute=True):
            completed = GuestCheckInOrchestrator.complete_session(
                ensured.session,
                self.reservation,
            )

        self.assertEqual(completed.session.status, GuestCheckInSessionStatus.COMPLETED)
        mock_delay.assert_called_once_with(self.reservation.pk, completed.session.pk)
