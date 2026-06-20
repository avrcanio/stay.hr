from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.integrations.whatsapp.guest_document_batch_reconcile import reconcile_guest_document_batch


class Command(BaseCommand):
    help = "Reconcile stuck guest WhatsApp document batch sessions (rematch, apply, finalize)."

    def add_arguments(self, parser):
        parser.add_argument("--reservation-id", type=int, default=None)
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Attempt apply when completeness is OK.",
        )
        parser.add_argument(
            "--re-prompt-confirm",
            action="store_true",
            help="Re-send Ja/Nein prompt for stuck AWAITING_CONFIRM sessions.",
        )

    def handle(self, *args, **options):
        result = reconcile_guest_document_batch(
            reservation_id=options.get("reservation_id"),
            apply=bool(options.get("apply")),
            re_prompt_confirm=bool(options.get("re_prompt_confirm")),
        )
        self.stdout.write(self.style.SUCCESS(str(result)))
