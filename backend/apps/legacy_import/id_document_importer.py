from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.legacy_import.legacy_models import LegacyIdDocument
from apps.legacy_import.mapping import LEGACY_DB_ALIAS
from apps.legacy_import.migrator import assert_legacy_db, legacy_db_configured
from apps.reservations.models import Guest, IdDocument
from apps.tenants.models import Tenant


@dataclass
class IdDocumentImportStats:
    files_copied: int = 0
    documents_created: int = 0
    documents_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def copy_id_document_media(*, source_root: Path, media_root: Path) -> int:
    """Copy id_documents/ tree from Uzorita media into Stay MEDIA_ROOT."""
    src = source_root / "id_documents"
    if not src.is_dir():
        raise FileNotFoundError(f"Uzorita id_documents not found: {src}")

    dst = media_root / "id_documents"
    copied = 0
    for src_file in src.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or src_file.stat().st_size != target.stat().st_size:
            shutil.copy2(src_file, target)
            copied += 1
    return copied


def _media_path_exists(media_root: Path, relative_path: str) -> bool:
    path = (relative_path or "").strip()
    if not path:
        return False
    return (media_root / path).is_file()


def _assign_image_field(document: IdDocument, field_name: str, relative_path: str) -> bool:
    path = (relative_path or "").strip()
    if not path:
        return False
    field = getattr(document, field_name)
    field.name = path
    return True


class UzoritaIdDocumentImporter:
    def __init__(
        self,
        *,
        tenant_slug: str = "uzorita",
        media_source: Path | None = None,
        skip_copy: bool = False,
        dry_run: bool = False,
    ):
        self.tenant_slug = tenant_slug
        self.media_source = media_source
        self.skip_copy = skip_copy
        self.dry_run = dry_run
        self.stats = IdDocumentImportStats()
        self._media_root = Path(settings.MEDIA_ROOT)

    def run(self) -> IdDocumentImportStats:
        if not legacy_db_configured():
            raise RuntimeError("UZORITA_DB_* is not configured.")
        assert_legacy_db()

        tenant = Tenant.objects.get(slug=self.tenant_slug)
        guest_by_legacy = {
            g.legacy_id: g
            for g in Guest.objects.filter(tenant=tenant, legacy_id__isnull=False)
        }

        with transaction.atomic():
            if not self.skip_copy and self.media_source is not None:
                self.stats.files_copied = copy_id_document_media(
                    source_root=self.media_source,
                    media_root=self._media_root,
                )

            for legacy in LegacyIdDocument.objects.using(LEGACY_DB_ALIAS).order_by("id"):
                guest = guest_by_legacy.get(legacy.guest_id)
                if guest is None:
                    self.stats.errors.append(
                        f"IdDocument {legacy.id}: guest legacy_id={legacy.guest_id} not in Stay"
                    )
                    continue

                paths = [
                    legacy.face_photo,
                    legacy.signature_photo,
                    legacy.front_photo or "",
                    legacy.back_photo or "",
                ]
                if not any(p.strip() for p in paths if p):
                    self.stats.documents_skipped += 1
                    continue

                if IdDocument.objects.filter(
                    guest=guest,
                    extracted_payload__uzorita_idocument_id=legacy.id,
                ).exists():
                    self.stats.documents_skipped += 1
                    continue

                missing = [
                    p
                    for p in paths
                    if p.strip() and not _media_path_exists(self._media_root, p.strip())
                ]
                if missing:
                    self.stats.errors.append(
                        f"IdDocument {legacy.id}: missing files: {', '.join(missing[:3])}"
                    )
                    continue

                payload = dict(legacy.extracted_payload or {})
                payload["uzorita_idocument_id"] = legacy.id
                document = IdDocument(
                    guest=guest,
                    image_path=legacy.image_path or f"uzorita:idocument:{legacy.id}",
                    extracted_payload=payload,
                )
                _assign_image_field(document, "face_photo", legacy.face_photo)
                _assign_image_field(document, "signature_photo", legacy.signature_photo)
                _assign_image_field(document, "front_photo", legacy.front_photo or "")
                _assign_image_field(document, "back_photo", legacy.back_photo or "")

                if self.dry_run:
                    self.stats.documents_created += 1
                    continue

                document.save()
                IdDocument.objects.filter(pk=document.pk).update(
                    created_at=legacy.created_at,
                    updated_at=legacy.updated_at,
                )
                self.stats.documents_created += 1

            if self.dry_run:
                transaction.set_rollback(True)

        return self.stats
