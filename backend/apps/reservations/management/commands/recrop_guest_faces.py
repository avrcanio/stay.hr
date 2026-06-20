"""Re-crop guest face photos from stored ID front images."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.reservations.document_intake_face import _coerce_bbox_dict, crop_face_jpeg
from apps.reservations.models import Guest, IdDocument


class Command(BaseCommand):
    help = "Re-crop face_photo on IdDocument from front_photo using OpenCV face detection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--guest-id",
            type=int,
            action="append",
            dest="guest_ids",
            help="Guest PK (repeatable).",
        )
        parser.add_argument(
            "--reservation-id",
            type=int,
            help="Re-crop all guests on this reservation.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Detect only; do not save.",
        )

    def handle(self, *args, **options):
        guest_ids: list[int] = list(options.get("guest_ids") or [])
        reservation_id = options.get("reservation_id")
        dry_run = bool(options.get("dry_run"))

        if reservation_id:
            guest_ids.extend(
                Guest.objects.filter(reservation_id=reservation_id).values_list("pk", flat=True)
            )

        if not guest_ids:
            self.stderr.write("Provide --guest-id and/or --reservation-id.")
            return

        updated = 0
        skipped = 0
        for guest_id in sorted(set(guest_ids)):
            doc = (
                IdDocument.objects.filter(guest_id=guest_id, front_photo__isnull=False)
                .exclude(front_photo="")
                .order_by("-id")
                .first()
            )
            if doc is None or not doc.front_photo:
                self.stdout.write(f"guest {guest_id}: no front_photo — skip")
                skipped += 1
                continue

            person = (doc.extracted_payload or {}).get("person") or {}
            bbox = _coerce_bbox_dict(person.get("face_bbox"))
            face_content = crop_face_jpeg(doc.front_photo.path, bbox)
            if face_content is None:
                self.stdout.write(f"guest {guest_id}: face crop failed — skip")
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f"guest {guest_id}: face detected (dry-run)")
                updated += 1
                continue

            if doc.face_photo:
                doc.face_photo.delete(save=False)
            doc.face_photo.save(f"guest_{guest_id}_face.jpg", face_content, save=True)
            self.stdout.write(f"guest {guest_id}: face_photo updated")
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Done: {updated} updated, {skipped} skipped"))
