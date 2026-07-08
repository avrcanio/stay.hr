from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction

from apps.properties.models import Property
from apps.reservations.booking_payout.csv_parser import BookingPayoutCsvParser
from apps.reservations.booking_payout.match import match_booking_payout_rows
from apps.reservations.booking_payout.types import PayoutPreviewResult
from apps.reservations.booking_payout.validate import (
    BookingPayoutValidationError,
    validate_booking_payout_rows,
)
from apps.reservations.booking_payout_models import (
    BookingPayoutImport,
    BookingPayoutImportStatus,
    BookingPayoutLine,
)
from apps.tenants.models import Tenant


def _duplicate_batch_errors(
    *,
    property_obj: Property,
    source_sha256: str,
    payout_id: str,
) -> list[str]:
    errors: list[str] = []
    if BookingPayoutImport.objects.filter(
        property_obj=property_obj,
        source_sha256=source_sha256,
    ).exists():
        errors.append(
            "Datoteka s istim SHA-256 već je uvezena za objekt "
            f"{property_obj.slug}. Otvorite postojeći import u listi."
        )
    existing = BookingPayoutImport.objects.filter(
        property_obj=property_obj,
        payout_id=payout_id,
    ).first()
    if existing is not None:
        errors.append(
            f"Payout ID {payout_id!r} već postoji za objekt {property_obj.slug} "
            f"(import #{existing.pk}, status={existing.status}). "
            f"Dupli upload nije potreban — otvorite postojeći import."
        )
    return errors


def preview_booking_payout_csv(
    content: bytes,
    *,
    tenant: Tenant,
    property_obj: Property,
    filename: str = "upload.csv",
    uploaded_by=None,
    persist: bool = True,
) -> tuple[PayoutPreviewResult, BookingPayoutImport | None]:
    parser = BookingPayoutCsvParser()
    rows, source_sha256 = parser.parse_bytes(content)

    batch_errors: list[str] = []
    try:
        validate_booking_payout_rows(rows)
    except BookingPayoutValidationError as exc:
        batch_errors.extend(exc.errors)

    preview_lines = match_booking_payout_rows(rows, tenant=tenant, property_obj=property_obj)
    first = rows[0]
    preview = PayoutPreviewResult(
        payout_id=first.payout_id,
        payout_date=first.payout_date,
        currency=first.currency,
        source_sha256=source_sha256,
        lines=preview_lines,
        batch_errors=batch_errors,
    )

    batch_errors.extend(
        _duplicate_batch_errors(
            property_obj=property_obj,
            source_sha256=source_sha256,
            payout_id=first.payout_id,
        )
    )
    preview.batch_errors = batch_errors

    if batch_errors or not persist:
        return preview, None

    with transaction.atomic():
        import_batch = BookingPayoutImport(
            tenant=tenant,
            property_obj=property_obj,
            payout_id=first.payout_id,
            payout_date=first.payout_date,
            currency=first.currency,
            source_sha256=source_sha256,
            status=BookingPayoutImportStatus.PARSED,
            uploaded_by=uploaded_by,
        )
        import_batch.source_file.save(filename, ContentFile(content), save=False)
        import_batch.save()

        line_models = [
            BookingPayoutLine(
                import_batch=import_batch,
                line_number=line.dto.line_number,
                reservation_id=line.reservation_id,
                booking_number=line.dto.booking_number,
                guest_name=line.dto.guest_name,
                check_in=line.dto.check_in,
                check_out=line.dto.check_out,
                gross_amount=line.dto.gross_amount,
                commission_amount=line.dto.commission_amount,
                service_fee=line.dto.service_fee,
                net_amount=line.dto.net_amount,
                currency=line.dto.currency,
                reservation_status=line.dto.reservation_status,
                match_status=line.match_status,
                source_row=line.dto.source_row,
                warnings=line.warnings,
            )
            for line in preview_lines
        ]
        BookingPayoutLine.objects.bulk_create(line_models)

    return preview, import_batch
