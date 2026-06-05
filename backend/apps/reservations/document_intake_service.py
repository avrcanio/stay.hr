"""Process document intake jobs: OCR, match, apply to guests."""

from __future__ import annotations

import logging
import mimetypes
import time
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.ai.document_ocr import DocumentOcrError, ocr_configured, run_document_batch_ocr
from apps.reservations.document_intake_face import crop_face_jpeg
from apps.reservations.document_intake_match import match_persons_to_guests, normalize_mrz_lines
from apps.reservations.guest_slots import ensure_guest_slots_for_intake
from apps.reservations.mrz_parse import normalize_residence_address, parse_sex_from_mrz
from apps.reservations.nationality_display import guest_nationality_iso2, normalize_country_iso2
from apps.reservations.document_photo_storage import (
    DOCUMENT_TYPE_NATIONAL_ID,
    DOCUMENT_TYPE_PASSPORT,
    document_photo_filename,
)
from apps.reservations.face_photo import guest_face_photo_url
from apps.reservations.models import (
    DocumentIntakeJob,
    DocumentIntakeJobStatus,
    DocumentScanLog,
    DocumentScanStatus,
    Guest,
    IdDocument,
    Reservation,
)

logger = logging.getLogger(__name__)


def _mime_for_path(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "image/jpeg"


def process_document_intake_job(job_id: int) -> None:
    job = DocumentIntakeJob.objects.prefetch_related("images").get(pk=job_id)
    if job.status == DocumentIntakeJobStatus.APPLIED:
        return

    job.status = DocumentIntakeJobStatus.PROCESSING
    job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])

    try:
        if not ocr_configured():
            raise DocumentOcrError("DOCUMENT_OCR_LLM_API_KEY is not configured")

        images = list(job.images.order_by("sort_order", "id"))
        if not images:
            raise DocumentOcrError("No images in job")

        bytes_list: list[bytes] = []
        mimes: list[str] = []
        for img in images:
            img.image.open("rb")
            try:
                bytes_list.append(img.image.read())
            finally:
                img.image.close()
            mimes.append(_mime_for_path(img.image.name))

        ocr_result = run_document_batch_ocr(image_bytes_list=bytes_list, mime_types=mimes)
        persons = ocr_result.get("persons") or []
        if not isinstance(persons, list):
            persons = []

        ocr_images = ocr_result.get("images") or []
        if isinstance(ocr_images, list):
            side_by_index = {
                int(item.get("index", -1)): str(item.get("side") or "")
                for item in ocr_images
                if isinstance(item, dict)
            }
            for img in images:
                side = side_by_index.get(img.sort_order, "")
                if side and img.detected_side != side:
                    img.detected_side = side
                    img.save(update_fields=["detected_side"])

        matches = match_persons_to_guests(tenant_id=job.tenant_id, persons=persons)

        job.ocr_result = ocr_result
        job.matches = matches
        job.status = DocumentIntakeJobStatus.DONE
        job.processed_at = timezone.now()
        job.save(
            update_fields=[
                "ocr_result",
                "matches",
                "status",
                "processed_at",
                "updated_at",
            ]
        )
    except DocumentOcrError as exc:
        job.status = DocumentIntakeJobStatus.FAILED
        job.error_message = str(exc)
        job.processed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "processed_at", "updated_at"])
    except Exception as exc:
        logger.exception("document intake job failed", extra={"job_id": job_id})
        job.status = DocumentIntakeJobStatus.FAILED
        job.error_message = str(exc)[:500]
        job.processed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "processed_at", "updated_at"])


def _target_reservation_ids_from_matches(matches: list[dict]) -> set[int]:
    ids: set[int] = set()
    for match in matches:
        if match.get("reservation_id"):
            ids.add(int(match["reservation_id"]))
            continue
        for candidate in match.get("candidates") or []:
            if candidate.get("match_type") == "name":
                ids.add(int(candidate["reservation_id"]))
    return ids


def _prepare_intake_matches(
    *,
    tenant_id: int,
    persons: list[dict],
    matches: list[dict],
) -> list[dict]:
    """Ensure guest slots and refresh matches before apply."""
    reservation_ids = _target_reservation_ids_from_matches(matches)
    if not reservation_ids and persons:
        reservation_ids = _target_reservation_ids_from_matches(
            match_persons_to_guests(tenant_id=tenant_id, persons=persons)
        )

    person_count = len(persons)
    for reservation_id in reservation_ids:
        reservation = Reservation.objects.prefetch_related("guests").get(pk=reservation_id)
        ensure_guest_slots_for_intake(
            tenant=reservation.tenant,
            reservation=reservation,
            min_count=person_count,
        )

    return match_persons_to_guests(tenant_id=tenant_id, persons=persons)


def apply_document_intake_job(
    job_id: int,
    *,
    selections: list[dict[str, Any]] | None = None,
    device_id: str = "",
    request=None,
) -> list[dict[str, Any]]:
    """Apply OCR results to guests. selections override auto matches.

    Updates guest fields, document photos, and scan log only — does not submit eVisitor.
    eVisitor check-in stays a separate manual step (POST .../evisitor-submit/).
    """
    job = DocumentIntakeJob.objects.prefetch_related("images").get(pk=job_id)
    if job.status not in {DocumentIntakeJobStatus.DONE, DocumentIntakeJobStatus.APPLIED}:
        raise ValueError("Job is not ready for apply")

    persons = job.ocr_result.get("persons") or []
    matches = list(job.matches or [])
    images = list(job.images.order_by("sort_order", "id"))

    selection_map = {
        int(item["person_index"]): item
        for item in (selections or [])
        if isinstance(item, dict) and "person_index" in item
    }

    if not selection_map:
        matches = _prepare_intake_matches(
            tenant_id=job.tenant_id,
            persons=persons,
            matches=matches,
        )
        job.matches = matches
        job.save(update_fields=["matches", "updated_at"])

    previously_applied_guest_ids = {
        int(item["guest_id"])
        for item in (job.applied_result or [])
        if isinstance(item, dict) and item.get("guest_id")
    }

    applied: list[dict[str, Any]] = []

    with transaction.atomic():
        for match in matches:
            idx = int(match.get("person_index", -1))
            if idx < 0 or idx >= len(persons):
                continue

            person = persons[idx]
            sel = selection_map.get(idx)
            reservation_id = None
            guest_id = None

            if sel:
                reservation_id = sel.get("reservation_id")
                guest_id = sel.get("guest_id")
            elif match.get("auto_apply"):
                reservation_id = match.get("reservation_id")
                guest_id = match.get("guest_id")

            if not reservation_id or not guest_id:
                continue

            if not sel and int(guest_id) in previously_applied_guest_ids:
                continue

            guest = Guest.objects.select_related("reservation").get(
                pk=guest_id,
                reservation_id=reservation_id,
                tenant_id=job.tenant_id,
            )
            reservation = guest.reservation

            result = _apply_person_to_guest(
                person=person,
                person_index=idx,
                guest=guest,
                reservation=reservation,
                images=images,
                device_id=device_id or job.device_id,
            )
            if request is not None:
                result["face_photo_url"] = guest_face_photo_url(guest, request)
            applied.append(result)

        if applied:
            merged = list(job.applied_result or [])
            merged_by_guest = {int(item["guest_id"]): item for item in merged if item.get("guest_id")}
            for item in applied:
                merged_by_guest[int(item["guest_id"])] = item
            job.applied_result = list(merged_by_guest.values())
        job.status = DocumentIntakeJobStatus.APPLIED
        job.save(update_fields=["applied_result", "status", "updated_at"])

    return applied


def _apply_person_to_guest(
    *,
    person: dict,
    person_index: int,
    guest: Guest,
    reservation: Reservation,
    images: list,
    device_id: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    doc_type = str(person.get("document_type") or "national_id").lower()
    tip = "passport" if doc_type == "passport" else "national_id"

    front_idx = person.get("front_image_index")
    back_idx = person.get("back_image_index")
    front_img = _image_at_index(images, front_idx)
    back_img = _image_at_index(images, back_idx)

    raw_payload = _build_scan_payload(person=person, device_id=device_id, tip=tip)
    guest_updates, suggested = _guest_updates_from_payload(raw_payload)

    scan_status = DocumentScanStatus.OK if guest_updates else DocumentScanStatus.FAILED
    error_message = "" if guest_updates else "Ne mogu mapirati OCR u polja gosta."

    scan_log = DocumentScanLog.objects.create(
        tenant_id=guest.tenant_id,
        reservation_id=reservation.pk,
        guest=guest,
        status=scan_status,
        method="OCR",
        device_id=device_id,
        scanned_at=timezone.now(),
        duration_ms=int((time.perf_counter() - started) * 1000),
        raw_payload=raw_payload,
        suggested_fields=suggested,
        corrected_fields={},
        error_message=error_message,
    )

    id_document_id = None
    if guest_updates:
        for field, value in guest_updates.items():
            setattr(guest, field, value)
        guest.save(update_fields=list(guest_updates.keys()) + ["updated_at", "name"])

    id_document = IdDocument.objects.create(
        guest=guest,
        image_path="",
        extracted_payload={"source": "document_intake", "person": person},
    )
    id_document_id = id_document.id
    id_document._passport_photo = tip == "passport"

    if front_img is not None:
        front_name = document_photo_filename(
            guest_id=guest.id,
            document_type=tip,
            side="front",
        )
        front_img.image.open("rb")
        try:
            id_document.front_photo.save(front_name, front_img.image, save=False)
        finally:
            front_img.image.close()

    if back_img is not None:
        back_name = document_photo_filename(
            guest_id=guest.id,
            document_type=tip,
            side="back",
        )
        back_img.image.open("rb")
        try:
            id_document.back_photo.save(back_name, back_img.image, save=False)
        finally:
            back_img.image.close()

    face_content = None
    if front_img is not None and front_img.image:
        bbox = person.get("face_bbox") if isinstance(person.get("face_bbox"), dict) else None
        face_content = crop_face_jpeg(front_img.image.path, bbox)

    if face_content is not None:
        id_document.face_photo.save(f"guest_{guest.pk}_face.jpg", face_content, save=False)

    id_document.save()

    guest.document_type = "Putovnica" if tip == "passport" else "Osobna iskaznica"
    guest.save(update_fields=["document_type", "updated_at", "name"])

    _sync_reservation_country_from_guest(guest=guest, reservation=reservation)

    return {
        "person_index": person_index,
        "guest_id": guest.pk,
        "reservation_id": reservation.pk,
        "guest_name": guest.name or f"{guest.first_name} {guest.last_name}".strip(),
        "scan_log_id": scan_log.pk,
        "scan_status": scan_status,
        "id_document_id": id_document_id,
        "updated_fields": list(guest_updates.keys()),
        "face_photo_saved": face_content is not None,
    }


def _sync_reservation_country_from_guest(*, guest: Guest, reservation: Reservation) -> None:
    """Set booker_country / primary guest so Hospira can show the flag."""
    guest_fields: list[str] = []
    if not guest.is_primary and not reservation.guests.filter(is_primary=True).exists():
        guest.is_primary = True
        guest_fields.append("is_primary")

    iso2 = guest_nationality_iso2(guest)
    reservation_fields: list[str] = []
    if iso2:
        if guest.is_primary or not (reservation.booker_country or "").strip():
            reservation.booker_country = iso2
            reservation_fields.append("booker_country")

    if guest_fields:
        guest.save(update_fields=guest_fields + ["updated_at"])
    if reservation_fields:
        reservation.save(update_fields=reservation_fields + ["updated_at"])


def _image_at_index(images: list, index: Any):
    if index is None:
        return None
    try:
        idx = int(index)
    except (TypeError, ValueError):
        return None
    if idx < 0 or idx >= len(images):
        return None
    return images[idx]


def _build_scan_payload(*, person: dict, device_id: str, tip: str) -> dict:
    mrz = normalize_mrz_lines(person)
    nat = str(person.get("nationality") or "").upper()[:3]
    issue = nat

    return {
        "metapodaci": {
            "metoda_ocitanja": "OCR",
            "vrijeme_skeniranja": timezone.now().isoformat(),
            "uredaj_id": device_id,
            "tip_dokumenta": tip,
        },
        "podaci_gosta": {
            "ime": str(person.get("given_names") or "").strip(),
            "prezime": str(person.get("surnames") or "").strip(),
            "broj_dokumenta": str(person.get("document_number") or "").strip(),
            "drzava_izdavanja": issue,
            "datum_rodenja": str(person.get("date_of_birth") or "").strip(),
            "datum_isteka": str(person.get("date_of_expiry") or "").strip(),
            "spol": str(person.get("sex") or "").strip(),
            "drzavljanstvo": nat,
            "adresa": str(person.get("address") or "").strip(),
        },
        "biometrija": {"fotografija_b64": "", "potpis_b64": ""},
        "sirovi_mrz": mrz,
    }


def _guest_updates_from_payload(raw_payload: dict) -> tuple[dict, dict]:
    guest_data = raw_payload.get("podaci_gosta") or {}

    def as_str(key: str) -> str:
        val = guest_data.get(key)
        return str(val).strip() if val is not None else ""

    updates: dict = {}
    first_name = as_str("ime")
    last_name = as_str("prezime")
    if first_name:
        updates["first_name"] = first_name
    if last_name:
        updates["last_name"] = last_name

    doc_no = as_str("broj_dokumenta")
    if doc_no:
        updates["document_number"] = doc_no

    sex = as_str("spol")
    if sex:
        updates["sex"] = sex

    dob = as_str("datum_rodenja")
    if dob:
        parsed = parse_date(dob)
        if parsed:
            updates["date_of_birth"] = parsed

    doe = as_str("datum_isteka")
    if doe:
        parsed = parse_date(doe)
        if parsed:
            updates["date_of_expiry"] = parsed

    nat_raw = as_str("drzavljanstvo").upper()
    iso2 = normalize_country_iso2(nat_raw)
    if iso2:
        updates["nationality"] = iso2

    issue_iso3 = as_str("drzava_izdavanja").upper()[:3]
    if issue_iso3:
        updates["document_country_iso3"] = issue_iso3
        issue_iso2 = normalize_country_iso2(issue_iso3)
        if issue_iso2:
            updates["document_country_iso2"] = issue_iso2

    adresa = as_str("adresa")
    if adresa:
        updates["address"] = normalize_residence_address(adresa)

    meta = raw_payload.get("metapodaci") or {}
    tip = str(meta.get("tip_dokumenta") or "").lower()
    if tip == "passport":
        updates["document_type"] = "Putovnica"
    elif tip == "national_id":
        updates["document_type"] = "Osobna iskaznica"

    mrz = str(raw_payload.get("sirovi_mrz") or "").strip()
    if mrz:
        updates["mrz_raw_text"] = mrz
        updates["mrz_verified"] = True
        if not updates.get("sex"):
            mrz_sex = parse_sex_from_mrz(mrz)
            if mrz_sex:
                updates["sex"] = mrz_sex

    suggested = {
        "first_name": first_name,
        "last_name": last_name,
        "document_number": doc_no,
        "nationality": iso2,
        "date_of_birth": dob,
        "address": updates.get("address") or adresa,
    }
    suggested = {k: v for k, v in suggested.items() if v}
    return updates, suggested


def format_ocr_summary(ocr_result: dict[str, Any]) -> str:
    """Plain-text dump of OCR output for reception review / manual parsing."""
    if not ocr_result:
        return ""

    lines: list[str] = []

    images = ocr_result.get("images") or []
    if isinstance(images, list):
        for img in images:
            if not isinstance(img, dict):
                continue
            idx = img.get("index", "?")
            side = img.get("side") or "unknown"
            lines.append(f"=== Slika {idx} ({side}) ===")
            ocr_text = (img.get("ocr_text") or "").strip()
            if ocr_text:
                lines.append(ocr_text)
            mrz = img.get("mrz_lines") or []
            if isinstance(mrz, list) and mrz:
                lines.append("MRZ:")
                lines.extend(str(line) for line in mrz if str(line).strip())
            lines.append("")

    persons = ocr_result.get("persons") or []
    if isinstance(persons, list):
        for i, person in enumerate(persons):
            if not isinstance(person, dict):
                continue
            lines.append(f"=== Osoba {i + 1} (parsirano) ===")
            field_labels = (
                ("given_names", "Ime"),
                ("surnames", "Prezime"),
                ("document_number", "Broj dokumenta"),
                ("nationality", "Nacionalnost"),
                ("date_of_birth", "Datum rođenja"),
                ("date_of_expiry", "Vrijedi do"),
                ("sex", "Spol"),
                ("address", "Adresa"),
                ("document_type", "Tip dokumenta"),
            )
            for key, label in field_labels:
                value = (person.get(key) or "").strip() if person.get(key) is not None else ""
                if value:
                    lines.append(f"{label}: {value}")
            mrz = person.get("mrz_lines") or []
            if isinstance(mrz, list) and mrz:
                lines.append("MRZ (osoba):")
                lines.extend(str(line) for line in mrz if str(line).strip())
            lines.append("")

    return "\n".join(lines).strip()


def job_to_dict(job: DocumentIntakeJob, *, request=None) -> dict[str, Any]:
    ocr_result = job.ocr_result or {}
    data: dict[str, Any] = {
        "job_id": job.pk,
        "status": job.status,
        "image_count": job.images.count(),
        "error_message": job.error_message or "",
        "processed_at": job.processed_at.isoformat() if job.processed_at else None,
        "ocr_result": ocr_result,
        "ocr_summary": format_ocr_summary(ocr_result),
        "matches": job.matches or [],
        "applied": job.applied_result or [],
        "created_at": job.created_at.isoformat(),
    }
    if request is not None and job.applied_result:
        for item in data["applied"]:
            guest_id = item.get("guest_id")
            reservation_id = item.get("reservation_id")
            if not guest_id or not reservation_id:
                continue
            try:
                guest = Guest.objects.get(pk=guest_id, reservation_id=reservation_id)
                item["face_photo_url"] = guest_face_photo_url(guest, request)
            except Guest.DoesNotExist:
                pass
    return data
