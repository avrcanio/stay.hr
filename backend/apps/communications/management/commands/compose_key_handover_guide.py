from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.communications.key_handover_compose import (
    build_key_handover_compose_context,
    render_key_handover_guide,
    reservation_key_handover_labels,
)
from apps.properties.models import SelfServiceMode
from apps.properties.self_service import is_self_service_active
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
        else:
            compose_context = build_key_handover_compose_context(reservation)

        body = render_key_handover_guide(reservation)
        lang = compose_context.get("language", "")
        active = is_self_service_active(prop, reservation.check_in)

        self.stdout.write(
            f"Reservation #{reservation.pk} ({reservation.booking_code or 'no code'})"
        )
        self.stdout.write(f"  Guest: {reservation.booker_name or '—'}")
        self.stdout.write(f"  Property: {prop.slug} (tenant {reservation.tenant.slug})")
        self.stdout.write(f"  self_service_mode: {prop.self_service_mode}")
        self.stdout.write(f"  self_service_active(check_in): {active}")
        self.stdout.write(f"  room_code: {room_code!r}  key_label: {key_label!r}")
        self.stdout.write(f"  language: {lang}")
        self.stdout.write("")

        if prop.self_service_mode == SelfServiceMode.OFF:
            self.stdout.write(
                self.style.WARNING(
                    "Property self_service_mode is off — key guide card will not appear on the portal."
                )
            )
        elif not active:
            self.stdout.write(
                self.style.WARNING(
                    "Self-service is not active for this check-in date — portal omits key_guide."
                )
            )

        if not body.strip():
            self.stdout.write(
                self.style.WARNING("(empty guide — check guest_info.guide sections)")
            )
            return

        self.stdout.write(body)
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Rendered {len(body)} characters ({body.count(chr(10)) + 1} lines). Not sent."
            )
        )
