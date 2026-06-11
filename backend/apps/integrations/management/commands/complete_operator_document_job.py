from django.core.management.base import BaseCommand, CommandError

from apps.integrations.whatsapp.operator_job_complete import complete_operator_document_job


class Command(BaseCommand):
    help = (
        "Replay operator WhatsApp document job: re-match OCR, apply guests, "
        "check-in, eVisitor, notify guest and operator."
    )

    def add_arguments(self, parser):
        parser.add_argument("--job-id", type=int, required=True, help="DocumentIntakeJob pk")
        parser.add_argument(
            "--reservation-id",
            type=int,
            default=None,
            help="Target reservation pk when match is ambiguous",
        )
        parser.add_argument(
            "--operator-wa-id",
            type=str,
            default="",
            help="Operator WhatsApp wa_id for success notification (default Toni)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Re-match and show plan without applying or sending messages",
        )
        parser.add_argument(
            "--guest-notify",
            type=str,
            choices=["default", "email-only", "skip"],
            default="default",
            help="Guest notification: default (WA first), email-only, skip",
        )

    def handle(self, *args, **options):
        job_id = options["job_id"]
        guest_notify_mode = (options.get("guest_notify") or "default").replace("-", "_")
        try:
            result = complete_operator_document_job(
                job_id,
                reservation_id=options.get("reservation_id"),
                operator_wa_id=(options.get("operator_wa_id") or "").strip() or None,
                dry_run=options["dry_run"],
                guest_notify_mode=guest_notify_mode,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if result.get("status") == "dry_run":
            self.stdout.write(self.style.WARNING("DRY RUN"))
            self.stdout.write(f"  reservation_id={result.get('reservation_id')}")
            self.stdout.write(f"  selections={result.get('selections')}")
            self.stdout.write(f"  images={result.get('image_count')}")
            for match in result.get("matches") or []:
                if isinstance(match, dict):
                    self.stdout.write(
                        f"  person {match.get('person_index')}: "
                        f"{match.get('person_name')!r} auto_apply={match.get('auto_apply')} "
                        f"res={match.get('reservation_id')}"
                    )
            return

        self.stdout.write(self.style.SUCCESS(f"Completed job #{result.get('job_id')}"))
        self.stdout.write(f"  reservation_id={result.get('reservation_id')}")
        self.stdout.write(f"  checkin={result.get('checkin')}")
        self.stdout.write(f"  evisitor_summary={result.get('evisitor_summary')}")
        for item in result.get("evisitor") or []:
            self.stdout.write(f"    eVisitor guest #{item.get('guest_id')}: {item.get('status')}")
        self.stdout.write(f"  guest_email={result.get('guest_email')}")
        self.stdout.write(f"  guest_whatsapp={result.get('guest_whatsapp')}")
        self.stdout.write(f"  operator_whatsapp={result.get('operator_whatsapp')}")
