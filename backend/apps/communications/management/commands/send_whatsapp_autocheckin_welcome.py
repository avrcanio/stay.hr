from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from apps.communications.whatsapp_autocheckin_tasks import (
    iter_due_autocheckin_reservations,
    send_welcome_template_for_reservation,
)
from apps.properties.models import Property
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Send WhatsApp welcome templates for reservations with check-in today "
        "(property whatsapp_autocheckin_* settings). Use --dry-run to preview."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="")
        parser.add_argument("--property-id", type=int, default=None)
        parser.add_argument(
            "--date",
            default="",
            help="Override check-in date (YYYY-MM-DD). Default: today in property timezone.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List candidates without sending.",
        )

    def handle(self, *args, **options):
        on_date: date | None = None
        if options["date"]:
            on_date = date.fromisoformat(options["date"])

        property_id = options["property_id"]
        tenant_slug = (options["tenant_slug"] or "").strip()
        dry_run = bool(options["dry_run"])

        if tenant_slug:
            tenant = Tenant.objects.filter(slug=tenant_slug).first()
            if tenant is None:
                self.stderr.write(self.style.ERROR(f"Tenant not found: {tenant_slug}"))
                return
            props = Property.objects.filter(
                tenant=tenant,
                whatsapp_autocheckin_enabled=True,
            )
            if property_id is not None:
                props = props.filter(pk=property_id)
        else:
            props = Property.objects.filter(whatsapp_autocheckin_enabled=True)
            if property_id is not None:
                props = props.filter(pk=property_id)

        if not props.exists():
            self.stdout.write(self.style.WARNING("No properties with autocheck-in enabled."))
            return

        reservations = iter_due_autocheckin_reservations(
            property_id=property_id,
            on_date=on_date,
        )
        if tenant_slug:
            reservations = [r for r in reservations if r.tenant.slug == tenant_slug]

        if not reservations:
            self.stdout.write("No due reservations.")
            return

        sent = skipped = failed = 0
        for reservation in reservations:
            outcome = send_welcome_template_for_reservation(reservation, dry_run=dry_run)
            status = outcome.get("status")
            code = reservation.booking_code or str(reservation.pk)
            if status == "sent":
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"Sent welcome → {code}"))
            elif status == "dry_run":
                sent += 1
                self.stdout.write(
                    f"[dry-run] {code}: template={outcome.get('template_name')} "
                    f"lang={outcome.get('language')} params={outcome.get('parameters')}"
                )
            elif status == "send_failed":
                failed += 1
                self.stderr.write(self.style.ERROR(f"Failed {code}: {outcome.get('detail')}"))
            else:
                skipped += 1
                self.stdout.write(f"Skipped {code}: {status} ({outcome.get('reason', '')})")

        verb = "Would send" if dry_run else "Sent"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} {sent}, skipped {skipped}, failed {failed}.")
        )

        if dry_run:
            self.stdout.write(
                "\nDeploy checklist:\n"
                "  1. python manage.py migrate\n"
                "  2. Admin → Property → enable WhatsApp autocheck-in + set time\n"
                "  3. python manage.py seed_uzorita_whatsapp_config (with template map)\n"
                "  4. ./scripts/deploy.sh (django + celery-worker + celery-beat)\n"
            )
