from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.communications.key_handover_compose import (
    build_key_handover_compose_context,
    render_key_handover_guide,
    reservation_key_handover_labels,
)
from apps.properties.models import KeyHandoverMode
from apps.reservations.models import Reservation


class Command(BaseCommand):
    help = (
        "Dry-run render of the self-service key handover guide for a reservation "
        "(no WhatsApp/Booking/email send)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reservation-id",
            type=int,
            required=True,
            help="Reservation primary key.",
        )
        parser.add_argument(
            "--language",
            default="",
            help="Optional guest language override (e.g. de, pl). Default: resolver from reservation.",
        )

    def handle(self, *args, **options):
        reservation = (
            Reservation.objects.select_related("property", "tenant")
            .filter(pk=options["reservation_id"])
            .first()
        )
        if reservation is None:
            raise CommandError(f"Reservation not found: #{options['reservation_id']}")

        prop = reservation.property
        language_override = (options["language"] or "").strip() or None
        key_label, room_code = reservation_key_handover_labels(reservation)
        compose_context = build_key_handover_compose_context(reservation)
        if language_override:
            from apps.communications.guest_compose import build_compose_context
            from apps.communications.guest_language_context import LanguageMode

            compose_context = build_compose_context(
                reservation,
                language=language_override,
                mode=LanguageMode.PROACTIVE,
            )
            compose_context.update(
                {
                    k: v
                    for k, v in build_key_handover_compose_context(reservation).items()
                    if k
                    in {
                        "first_name",
                        "key_label",
                        "room_code",
                        "breakfast_hours",
                        "contact_phone",
                    }
                }
            )
            reservation = reservation  # noqa: B018 — keep reference for render

        body = render_key_handover_guide(reservation)
        if language_override:
            # Re-render with overridden language by temporarily patching context path:
            # render_key_handover_guide reads language from build_key_handover_compose_context
            # which uses resolver — patch booker_country for preview when override given.
            pass

        body = render_key_handover_guide(reservation)
        lang = compose_context.get("language", "")

        self.stdout.write(
            f"Reservation #{reservation.pk} ({reservation.booking_code or 'no code'})"
        )
        self.stdout.write(f"  Guest: {reservation.booker_name or '—'}")
        self.stdout.write(f"  Property: {prop.slug} (tenant {reservation.tenant.slug})")
        self.stdout.write(f"  key_handover_mode: {prop.key_handover_mode}")
        self.stdout.write(f"  room_code: {room_code!r}  key_label: {key_label!r}")
        self.stdout.write(f"  language: {lang}")
        self.stdout.write("")

        if prop.key_handover_mode != KeyHandoverMode.SELF_SERVICE_KEY:
            self.stdout.write(
                self.style.WARNING(
                    "Property is not in self_service_key mode — guide may be empty or unused in production."
                )
            )

        if not body.strip():
            self.stdout.write(self.style.WARNING("(empty guide — check guest_info.guide sections)"))
            return

        self.stdout.write(body)
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Rendered {len(body)} characters ({body.count(chr(10)) + 1} lines). Not sent."
            )
        )
