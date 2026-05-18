from __future__ import annotations

from django.utils import timezone

DOCUMENT_TYPE_PASSPORT = "passport"
DOCUMENT_TYPE_NATIONAL_ID = "national_id"


def _photo_timestamp() -> str:
    return timezone.localtime().strftime("%d%m%y%H%M")


def document_photo_filename(*, guest_id: int, document_type: str, side: str) -> str:
    ts = _photo_timestamp()
    if document_type == DOCUMENT_TYPE_PASSPORT:
        return f"{ts}_{guest_id}_pass.jpg"
    if side == "front":
        return f"{ts}_{guest_id}_frontID.jpg"
    return f"{ts}_{guest_id}_backID.jpg"
