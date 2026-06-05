from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.integrations.channex.client import ChannexClient
from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.message_service import find_reservation_for_channex_booking
from apps.integrations.models import ChannexReview, IntegrationConfig
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)

AIRBNB_OTA = "AirBNB"
DEFAULT_PAGE_SIZE = 25


def channex_review_id_from_payload(payload: dict[str, Any]) -> str:
    for key in ("id", "channex_review_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    raise ChannexBookingIngestError("Channex review payload missing id.")


def _flatten_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
    attrs = payload.get("attributes")
    if isinstance(attrs, dict):
        merged = dict(attrs)
        if payload.get("id") and not merged.get("id"):
            merged["id"] = payload["id"]
        booking = (payload.get("relationships") or {}).get("booking") or {}
        booking_data = booking.get("data") if isinstance(booking, dict) else None
        if isinstance(booking_data, dict) and booking_data.get("id"):
            merged.setdefault("booking_id", str(booking_data["id"]))
        return merged
    return payload


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    parsed = parse_datetime(str(raw).replace("Z", "+00:00"))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _parse_score(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _guest_name(payload: dict[str, Any]) -> str:
    return str(
        payload.get("guest_name")
        or payload.get("reviewer_name")
        or ""
    ).strip()


def _review_fields_from_payload(
    flat: dict[str, Any],
    *,
    reservation: Reservation | None,
) -> dict[str, Any]:
    booking_id = str(flat.get("booking_id") or "").strip()
    return {
        "channex_booking_id": booking_id,
        "reservation": reservation,
        "ota": str(flat.get("ota") or "").strip(),
        "ota_reservation_id": str(flat.get("ota_reservation_id") or "").strip(),
        "ota_review_id": str(flat.get("ota_review_id") or "").strip(),
        "guest_name": _guest_name(flat),
        "content": str(flat.get("content") or flat.get("raw_content") or "").strip(),
        "reply": str(flat.get("reply") or "").strip(),
        "overall_score": _parse_score(flat.get("overall_score") or flat.get("ota_overall_score")),
        "scores": flat.get("scores") if isinstance(flat.get("scores"), list) else [],
        "tags": flat.get("tags") if isinstance(flat.get("tags"), list) else [],
        "is_replied": bool(flat.get("is_replied")),
        "is_hidden": bool(flat.get("is_hidden")),
        "expired_at": _parse_dt(flat.get("expired_at")),
        "received_at": _parse_dt(flat.get("received_at") or flat.get("inserted_at")),
        "reply_sent_at": _parse_dt(flat.get("reply_sent_at")),
        "reply_scheduled_at": _parse_dt(flat.get("reply_scheduled_at")),
        "raw_payload": flat,
    }


def _extract_review_rows(api_response: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in api_response.get("data") or []:
        if isinstance(item, dict):
            rows.append(_flatten_review_payload(item))
    data = api_response.get("data")
    if isinstance(data, dict):
        rows.append(_flatten_review_payload(data))
    return rows


def upsert_channex_review_from_payload(
    *,
    tenant: Tenant,
    integration: IntegrationConfig,
    payload: dict[str, Any],
    reservation: Reservation | None = None,
) -> tuple[ChannexReview, bool, bool]:
    """Return (row, created, content_just_arrived)."""
    flat = _flatten_review_payload(payload)
    review_id = channex_review_id_from_payload(flat)
    booking_id = str(flat.get("booking_id") or "").strip()
    if reservation is None and booking_id:
        reservation = find_reservation_for_channex_booking(tenant, booking_id)

    field_values = _review_fields_from_payload(flat, reservation=reservation)
    existing = ChannexReview.objects.filter(channex_review_id=review_id).first()
    if existing is None:
        row = ChannexReview.objects.create(
            tenant=tenant,
            integration=integration,
            channex_review_id=review_id,
            **field_values,
        )
        if reservation is None and booking_id:
            logger.warning(
                "channex review stored without reservation link",
                extra={
                    "tenant_slug": tenant.slug,
                    "booking_id": booking_id,
                    "review_id": review_id,
                },
            )
        return row, True, bool(field_values["content"])

    had_content = bool((existing.content or "").strip())
    new_content = field_values["content"]
    content_just_arrived = bool(new_content) and not had_content

    for key, value in field_values.items():
        setattr(existing, key, value)
    existing.integration = integration
    existing.save()
    return existing, False, content_just_arrived


def _should_notify_review(
    *,
    created: bool,
    content_just_arrived: bool,
    event: str,
    row: ChannexReview,
) -> bool:
    if not row.reservation_id or row.is_replied:
        return False
    if created and event == "review":
        return True
    if event == "updated_review" and content_just_arrived:
        return True
    return False


def process_channex_review_webhook(
    integration_row: IntegrationConfig,
    *,
    property_id: str,
    body: dict[str, Any],
    event: str,
) -> dict[str, Any]:
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ChannexBookingIngestError("Channex review webhook missing payload.")

    tenant = integration_row.tenant
    booking_id = str(payload.get("booking_id") or "").strip()
    reservation = find_reservation_for_channex_booking(tenant, booking_id) if booking_id else None
    row, created, content_just_arrived = upsert_channex_review_from_payload(
        tenant=tenant,
        integration=integration_row,
        payload=payload,
        reservation=reservation,
    )
    logger.info(
        "channex review webhook processed",
        extra={
            "tenant_slug": tenant.slug,
            "property_id": property_id,
            "event": event,
            "booking_id": booking_id,
            "review_id": row.channex_review_id,
            "review_created": created,
            "reservation_id": row.reservation_id,
        },
    )
    if _should_notify_review(
        created=created,
        content_just_arrived=content_just_arrived,
        event=event,
        row=row,
    ):
        from apps.core.tasks import notify_guest_review_inbound

        notify_guest_review_inbound.delay(
            row.reservation_id,
            review_id=row.pk,
            ota=row.ota or "",
            score_preview=str(row.overall_score) if row.overall_score is not None else "",
            content_preview=(row.content or "")[:200],
        )
    return {
        "review_id": row.channex_review_id,
        "created": created,
        "reservation_id": row.reservation_id,
    }


def sync_reviews_from_channex(
    integration_row: IntegrationConfig,
    *,
    client: ChannexClient | None = None,
    max_pages: int = 5,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[ChannexReview]:
    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    if not config.property_id:
        raise ChannexBookingIngestError("Channex property_id is not configured.")

    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)

    stored: list[ChannexReview] = []
    try:
        for page in range(1, max_pages + 1):
            response = client.list_reviews(
                params={
                    "filter[property_id]": config.property_id,
                    "pagination[page]": page,
                    "pagination[limit]": page_size,
                    "order[by]": "received_at",
                    "order[direction]": "desc",
                }
            )
            rows = _extract_review_rows(response)
            if not rows:
                break
            for row_payload in rows:
                review, _created, _content = upsert_channex_review_from_payload(
                    tenant=integration_row.tenant,
                    integration=integration_row,
                    payload=row_payload,
                )
                stored.append(review)
            meta = response.get("meta") if isinstance(response.get("meta"), dict) else {}
            total_pages = int(meta.get("total") or 0)
            if page * page_size >= total_pages and total_pages > 0:
                break
            if len(rows) < page_size:
                break
    finally:
        if owns_client and client is not None:
            client.close()
    return stored


def _reviews_queryset(tenant: Tenant) -> QuerySet[ChannexReview]:
    return ChannexReview.objects.filter(tenant=tenant).select_related("reservation")


def list_reviews_for_property(
    integration_row: IntegrationConfig,
    *,
    unreplied_only: bool = False,
    ota: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    sync_if_empty: bool = True,
    force_sync: bool = False,
    client: ChannexClient | None = None,
) -> tuple[list[ChannexReview], int]:
    tenant = integration_row.tenant
    qs = _reviews_queryset(tenant)
    if unreplied_only:
        qs = qs.filter(is_replied=False)
    ota_filter = (ota or "").strip()
    if ota_filter:
        qs = qs.filter(ota__iexact=ota_filter)

    if force_sync or (sync_if_empty and not qs.exists()):
        sync_reviews_from_channex(integration_row, client=client)
        qs = _reviews_queryset(tenant)
        if unreplied_only:
            qs = qs.filter(is_replied=False)
        if ota_filter:
            qs = qs.filter(ota__iexact=ota_filter)

    total = qs.count()
    offset = max(page - 1, 0) * page_size
    rows = list(qs.order_by("-received_at", "-created_at")[offset : offset + page_size])
    return rows, total


def list_reviews_for_reservation(
    integration_row: IntegrationConfig,
    reservation: Reservation,
    *,
    sync_if_empty: bool = True,
    force_sync: bool = False,
    client: ChannexClient | None = None,
) -> list[ChannexReview]:
    qs = ChannexReview.objects.filter(
        tenant=reservation.tenant,
        reservation=reservation,
    )
    if force_sync or (sync_if_empty and not qs.exists()):
        sync_reviews_from_channex(integration_row, client=client, max_pages=10)
        qs = ChannexReview.objects.filter(
            tenant=reservation.tenant,
        ).filter(Q(reservation=reservation) | Q(channex_booking_id__in=_booking_ids_for_reservation(reservation)))
    return list(qs.order_by("-received_at", "-created_at"))


def _booking_ids_for_reservation(reservation: Reservation) -> list[str]:
    from apps.integrations.channex.booking_service import parse_channex_booking_id

    booking_id = parse_channex_booking_id(reservation.external_id)
    return [booking_id] if booking_id else []


def get_review_for_tenant(tenant: Tenant, review_pk: int) -> ChannexReview | None:
    return (
        _reviews_queryset(tenant)
        .filter(pk=review_pk)
        .first()
    )


def review_guest_review_allowed(row: ChannexReview) -> bool:
    return row.ota == AIRBNB_OTA and row.is_hidden


def review_reply_allowed(row: ChannexReview) -> bool:
    if row.is_replied:
        return False
    if row.expired_at and row.expired_at <= timezone.now():
        return False
    if row.ota == AIRBNB_OTA and row.is_hidden:
        return False
    return True


def reply_to_review(
    integration_row: IntegrationConfig,
    row: ChannexReview,
    reply_text: str,
    *,
    client: ChannexClient | None = None,
) -> ChannexReview:
    text = (reply_text or "").strip()
    if not text:
        raise ChannexBookingIngestError("Reply text is required.")
    if not review_reply_allowed(row):
        raise ChannexBookingIngestError("This review cannot be replied to.")

    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)

    try:
        response = client.reply_to_review(row.channex_review_id, text)
        rows = _extract_review_rows(response)
        if rows:
            row, _created, _content = upsert_channex_review_from_payload(
                tenant=row.tenant,
                integration=integration_row,
                payload=rows[0],
                reservation=row.reservation,
            )
        else:
            row.reply = text
            row.is_replied = True
            row.reply_sent_at = timezone.now()
            row.save(update_fields=["reply", "is_replied", "reply_sent_at", "updated_at"])
        return row
    except ChannexApiError:
        raise
    finally:
        if owns_client and client is not None:
            client.close()


def submit_airbnb_guest_review(
    integration_row: IntegrationConfig,
    row: ChannexReview,
    *,
    scores: list[dict[str, Any]],
    public_review: str = "",
    private_review: str = "",
    is_reviewee_recommended: bool = True,
    tags: list[str] | None = None,
    client: ChannexClient | None = None,
) -> ChannexReview:
    if row.ota != AIRBNB_OTA:
        raise ChannexBookingIngestError("Guest review is only supported for Airbnb reviews.")
    if not scores:
        raise ChannexBookingIngestError("At least one score category is required.")

    config = ChannexRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    owns_client = client is None
    if owns_client:
        client = ChannexClient(config)

    payload = {
        "review": {
            "scores": scores,
            "public_review": (public_review or "").strip(),
            "private_review": (private_review or "").strip(),
            "is_reviewee_recommended": is_reviewee_recommended,
            "tags": tags or [],
        }
    }

    try:
        response = client.submit_guest_review(row.channex_review_id, payload)
        rows = _extract_review_rows(response)
        if rows:
            row, _created, _content = upsert_channex_review_from_payload(
                tenant=row.tenant,
                integration=integration_row,
                payload=rows[0],
                reservation=row.reservation,
            )
        return row
    except ChannexApiError:
        raise
    finally:
        if owns_client and client is not None:
            client.close()


def serialize_channex_review(row: ChannexReview) -> dict[str, Any]:
    reservation = row.reservation
    booking_code = None
    if reservation is not None:
        booking_code = reservation.booking_code or str(reservation.pk)
    return {
        "id": row.pk,
        "channex_review_id": row.channex_review_id,
        "reservation_id": row.reservation_id,
        "booking_code": booking_code,
        "ota": row.ota,
        "ota_reservation_id": row.ota_reservation_id,
        "guest_name": row.guest_name,
        "overall_score": float(row.overall_score) if row.overall_score is not None else None,
        "scores": row.scores,
        "tags": row.tags,
        "content": row.content,
        "reply": row.reply or None,
        "is_replied": row.is_replied,
        "is_hidden": row.is_hidden,
        "expired_at": row.expired_at.isoformat() if row.expired_at else None,
        "received_at": row.received_at.isoformat() if row.received_at else None,
        "reply_sent_at": row.reply_sent_at.isoformat() if row.reply_sent_at else None,
        "can_reply": review_reply_allowed(row),
        "can_submit_guest_review": review_guest_review_allowed(row),
    }
