from __future__ import annotations

from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.integrations.whatsapp.operator_job_complete import complete_operator_document_job
from apps.integrations.whatsapp.whatsapp_operator_service import (
    _ACTIVE_COLLECT_STATUSES,
    _pg_advisory_xact_lock_operator,
    consolidate_operator_collect_sessions,
    merge_images_into_operator_job,
)
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobSource,
    Guest,
    Reservation,
    WhatsAppOperatorSession,
    WhatsAppOperatorSessionStatus,
)
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Merge stray operator WhatsApp sessions/jobs, optionally OCR+apply+check-in "
        "(reconcile race-split document batches)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", type=str, default="uzorita")
        parser.add_argument("--operator-wa-id", type=str, required=True)
        parser.add_argument("--reservation-id", type=int, default=None)
        parser.add_argument(
            "--guest-name",
            type=str,
            default="",
            help="Partial guest/booker name to resolve reservation (e.g. Režić)",
        )
        parser.add_argument(
            "--since",
            type=str,
            default="",
            help="ISO datetime or date — only sessions/jobs updated since (default: 24h ago)",
        )
        parser.add_argument(
            "--merge-only",
            action="store_true",
            help="Only merge sessions/images; do not OCR/apply/check-in",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--guest-notify",
            type=str,
            choices=["default", "email-only", "skip"],
            default="default",
            help="Guest notification: default (WA first), email-only, skip",
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            raise CommandError(f"Tenant not found: {options['tenant_slug']}")

        operator_wa_id = (options["operator_wa_id"] or "").strip()
        if not operator_wa_id:
            raise CommandError("--operator-wa-id is required")

        since = self._parse_since(options.get("since") or "")
        guest_notify_mode = (options.get("guest_notify") or "default").replace("-", "_")

        sessions = list(
            WhatsAppOperatorSession.objects.filter(
                tenant_id=tenant.pk,
                operator_wa_id=operator_wa_id,
                updated_at__gte=since,
            )
            .select_related("job")
            .order_by("-updated_at", "-id")
        )
        job_ids = {s.job_id for s in sessions}
        jobs = list(
            DocumentIntakeJob.objects.filter(
                tenant_id=tenant.pk,
                source=DocumentIntakeJobSource.WHATSAPP_OPERATOR,
                pk__in=job_ids,
            ).prefetch_related("images")
        )

        if not jobs:
            raise CommandError(
                f"No operator jobs found for wa_id={operator_wa_id} since {since.isoformat()}"
            )

        reservation_id = options.get("reservation_id")
        if reservation_id is None and (options.get("guest_name") or "").strip():
            reservation_id = self._resolve_reservation_by_name(
                tenant_id=tenant.pk,
                name=(options.get("guest_name") or "").strip(),
            )

        mergeable_jobs = [
            j
            for j in jobs
            if j.reservation_id is None or j.reservation_id == reservation_id
        ]
        if not mergeable_jobs:
            mergeable_jobs = jobs

        canonical_job = max(mergeable_jobs, key=lambda j: (j.images.count(), j.pk))
        other_jobs = [
            j
            for j in mergeable_jobs
            if j.pk != canonical_job.pk
            and (j.reservation_id is None or j.reservation_id == reservation_id)
        ]

        active_sessions = [s for s in sessions if s.status in _ACTIVE_COLLECT_STATUSES]
        canonical_session = None
        if active_sessions:
            canonical_session = max(
                active_sessions,
                key=lambda s: (s.job.images.count(), s.last_activity_at, s.pk),
            )
            if canonical_session.job_id != canonical_job.pk:
                canonical_job = canonical_session.job
                other_jobs = [j for j in jobs if j.pk != canonical_job.pk]

        reservation_id = options.get("reservation_id")
        plan = {
            "tenant_id": tenant.pk,
            "operator_wa_id": operator_wa_id,
            "since": since.isoformat(),
            "canonical_job_id": canonical_job.pk,
            "canonical_session_id": canonical_session.pk if canonical_session else None,
            "other_job_ids": [j.pk for j in other_jobs],
            "image_count_before": canonical_job.images.count(),
            "reservation_id": reservation_id,
            "guest_notify_mode": guest_notify_mode,
        }

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN"))
            for key, value in plan.items():
                self.stdout.write(f"  {key}={value}")
            return

        with transaction.atomic():
            _pg_advisory_xact_lock_operator(tenant.pk, operator_wa_id)
            if canonical_session is not None:
                canonical_session = consolidate_operator_collect_sessions(
                    tenant_id=tenant.pk,
                    operator_wa_id=operator_wa_id,
                    canonical_session=canonical_session,
                )
                canonical_job = canonical_session.job

            moved = merge_images_into_operator_job(canonical_job, other_jobs)
            plan["images_merged"] = moved
            plan["image_count_after"] = canonical_job.images.count()

        self.stdout.write(f"Canonical job #{canonical_job.pk} images={canonical_job.images.count()}")

        if options["merge_only"]:
            self.stdout.write(self.style.SUCCESS("Merge only — done."))
            return

        if reservation_id is None:
            raise CommandError(
                "Pass --reservation-id or --guest-name for complete after merge"
            )

        result = complete_operator_document_job(
            canonical_job.pk,
            reservation_id=reservation_id,
            operator_wa_id=operator_wa_id,
            guest_notify_mode=guest_notify_mode,
        )
        self.stdout.write(self.style.SUCCESS(f"Completed: {result.get('status')}"))
        self.stdout.write(f"  reservation_id={result.get('reservation_id')}")
        self.stdout.write(f"  checkin={result.get('checkin')}")
        self.stdout.write(f"  guest_notify={result.get('guest_notify')}")
        self.stdout.write(f"  operator_whatsapp={result.get('operator_whatsapp')}")

    def _parse_since(self, raw: str) -> datetime:
        if not raw:
            return timezone.now() - timedelta(hours=24)
        try:
            if len(raw) <= 10:
                dt = datetime.fromisoformat(raw)
                return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except ValueError as exc:
            raise CommandError(f"Invalid --since: {raw}") from exc

    def _resolve_reservation_by_name(self, *, tenant_id: int, name: str) -> int:
        needle = name.lower()
        guests = Guest.objects.filter(tenant_id=tenant_id).select_related("reservation")
        for guest in guests:
            display = (guest.name or f"{guest.first_name} {guest.last_name}").strip().lower()
            if needle in display:
                return guest.reservation_id

        reservations = Reservation.objects.filter(tenant_id=tenant_id)
        for res in reservations:
            if needle in (res.booker_name or "").lower():
                return res.pk

        raise CommandError(f"No reservation found for guest-name={name!r}")
