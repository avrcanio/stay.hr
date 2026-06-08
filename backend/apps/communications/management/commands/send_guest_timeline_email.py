from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.communications.guest_message_send import (
    default_email_subject,
    send_guest_email_with_timeline_record,
)
from apps.communications.models import GuestMessageIntent, GuestOutboundMessageStatus
from apps.reservations.models import Reservation


class Command(BaseCommand):
    help = (
        "Send guest SMTP email and record GuestOutboundMessage for reception timeline. "
        "Use for manual/ops sends instead of calling send_guest_text_email in shell."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reservation-id",
            type=int,
            required=True,
            help="Reservation primary key.",
        )
        parser.add_argument(
            "--body",
            type=str,
            required=True,
            help="Plain-text email body.",
        )
        parser.add_argument(
            "--body-html",
            type=str,
            default="",
            help="Optional HTML alternative (e.g. WhatsApp button).",
        )
        parser.add_argument(
            "--subject",
            type=str,
            default="",
            help="Email subject (default: reservation subject template).",
        )
        parser.add_argument(
            "--intent",
            type=str,
            default=GuestMessageIntent.CUSTOM,
            choices=[c.value for c in GuestMessageIntent],
            help="GuestMessageDraft intent (default: custom).",
        )
        parser.add_argument(
            "--hint",
            type=str,
            default="",
            help="Optional draft hint for audit.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate reservation/recipient only; do not send.",
        )

    def handle(self, *args, **options):
        reservation = (
            Reservation.objects.filter(pk=options["reservation_id"])
            .select_related("tenant", "property")
            .first()
        )
        if reservation is None:
            raise CommandError(f"Reservation not found: {options['reservation_id']}")

        body = (options["body"] or "").strip()
        if not body:
            raise CommandError("--body is required")

        subject = (options["subject"] or "").strip() or None
        body_html = (options["body_html"] or "").strip() or None

        if options["dry_run"]:
            self.stdout.write(
                f"dry_run reservation={reservation.pk} "
                f"subject={default_email_subject(reservation)!r} "
                f"body_len={len(body)} html={bool(body_html)}"
            )
            return

        outbound = send_guest_email_with_timeline_record(
            reservation,
            body,
            subject=subject,
            body_html=body_html,
            intent=options["intent"],
            hint=options["hint"],
        )
        if outbound.status != GuestOutboundMessageStatus.SENT:
            raise CommandError(outbound.error_message or "send_failed")

        self.stdout.write(
            f"sent outbound_id={outbound.pk} to={outbound.to_email} "
            f"reservation={reservation.pk}"
        )
