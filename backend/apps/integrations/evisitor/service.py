from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from apps.integrations.evisitor.client import EvisitorClient
from apps.integrations.evisitor.exceptions import (
    EvisitorApiError,
    EvisitorConfigError,
    EvisitorValidationError,
)
from apps.integrations.evisitor.mapper import (
    build_check_in_payload,
    build_check_out_payload,
    mask_payload_for_log,
)
from apps.integrations.evisitor.messages import (
    format_evisitor_user_message,
    parse_existing_registration_id,
    resolve_evisitor_error_message,
)
from apps.integrations.evisitor.eligibility import guest_requires_evisitor
from apps.integrations.evisitor.resolver import resolve_evisitor_config
from apps.reservations.models import EvisitorGuestStatus, EvisitorSubmission, Guest


def _resolve_for_guest(guest: Guest):
    guest = Guest.objects.select_related("reservation", "reservation__property", "tenant").get(
        pk=guest.pk
    )
    return resolve_evisitor_config(guest.tenant, guest.reservation.property)


def submit_guest_checkin(
    guest: Guest,
    *,
    force_retry: bool = False,
    time_stay_from: str | None = None,
) -> EvisitorSubmission:
    config = _resolve_for_guest(guest)
    guest = Guest.objects.select_related("reservation").get(pk=guest.pk)

    if not guest_requires_evisitor(guest):
        raise EvisitorValidationError(
            "eVisitor prijava nije potrebna za goste mlađe od 18 godina."
        )

    if guest.evisitor_status == EvisitorGuestStatus.SENT and not force_retry:
        return (
            EvisitorSubmission.objects.filter(
                guest=guest, status=EvisitorGuestStatus.SENT
            )
            .order_by("-created_at")
            .first()
        )

    registration_id = uuid.uuid4()
    if guest.evisitor_registration_id and guest.evisitor_status == EvisitorGuestStatus.FAILED:
        if not force_retry:
            registration_id = guest.evisitor_registration_id
    elif guest.evisitor_registration_id and guest.evisitor_status == EvisitorGuestStatus.SENT:
        registration_id = guest.evisitor_registration_id

    payload = build_check_in_payload(
        guest,
        config=config,
        registration_id=registration_id,
        time_stay_from=time_stay_from,
    )
    masked = mask_payload_for_log(payload)

    submission = EvisitorSubmission.objects.create(
        tenant=guest.tenant,
        guest=guest,
        registration_id=registration_id,
        status=EvisitorGuestStatus.PENDING,
        request_payload=masked,
        created_at=timezone.now(),
    )

    Guest.objects.filter(pk=guest.pk).update(
        evisitor_status=EvisitorGuestStatus.PENDING,
        evisitor_registration_id=registration_id,
    )

    client = EvisitorClient(config)
    try:
        client.login()
        client.execute_action("CheckInTourist", payload)
    except (EvisitorApiError, EvisitorValidationError, EvisitorConfigError) as exc:
        user_msg = getattr(exc, "user_message", "") or str(exc)
        system_msg = getattr(exc, "system_message", "") or ""
        field_errors = getattr(exc, "field_errors", None)
        if field_errors:
            user_msg = "; ".join(f"{k}: {v}" for k, v in field_errors.items())

        existing_id = parse_existing_registration_id(user_msg)
        if existing_id:
            readable = format_evisitor_user_message(user_msg) or user_msg
            now = timezone.now()
            submission.status = EvisitorGuestStatus.SENT
            submission.submitted_at = now
            submission.registration_id = uuid.UUID(existing_id)
            submission.error_user_message = readable[:2000]
            submission.error_system_message = system_msg[:2000]
            submission.response_payload = {
                "ok": True,
                "recovered": True,
                "existing_registration_id": existing_id,
                "message": readable,
            }
            submission.save(
                update_fields=[
                    "status",
                    "submitted_at",
                    "registration_id",
                    "error_user_message",
                    "error_system_message",
                    "response_payload",
                ]
            )
            Guest.objects.filter(pk=guest.pk).update(
                evisitor_status=EvisitorGuestStatus.SENT,
                evisitor_registration_id=existing_id,
            )
            return submission

        submission.status = EvisitorGuestStatus.FAILED
        submission.error_user_message = resolve_evisitor_error_message(
            user_message=user_msg,
            system_message=system_msg,
            fallback=str(exc),
        )[:2000]
        submission.error_system_message = system_msg[:2000]
        submission.response_payload = {
            "error": user_msg,
            "system": system_msg,
        }
        submission.save(
            update_fields=[
                "status",
                "error_user_message",
                "error_system_message",
                "response_payload",
            ]
        )
        Guest.objects.filter(pk=guest.pk).update(
            evisitor_status=EvisitorGuestStatus.FAILED,
        )
        raise
    finally:
        try:
            client.logout()
        finally:
            client.close()

    now = timezone.now()
    submission.status = EvisitorGuestStatus.SENT
    submission.submitted_at = now
    submission.response_payload = {"ok": True}
    submission.save(update_fields=["status", "submitted_at", "response_payload"])

    with transaction.atomic():
        Guest.objects.filter(pk=guest.pk).update(
            evisitor_status=EvisitorGuestStatus.SENT,
            evisitor_registration_id=registration_id,
        )

    return submission


def _record_checkout_failure(
    submission: EvisitorSubmission,
    guest: Guest,
    exc: Exception,
) -> None:
    user_msg = getattr(exc, "user_message", "") or str(exc)
    system_msg = getattr(exc, "system_message", "") or ""
    field_errors = getattr(exc, "field_errors", None)
    if field_errors:
        user_msg = "; ".join(f"{k}: {v}" for k, v in field_errors.items())

    submission.status = EvisitorGuestStatus.FAILED
    submission.error_user_message = user_msg[:2000]
    submission.error_system_message = system_msg[:2000]
    submission.response_payload = {"error": user_msg, "system": system_msg}
    submission.save(
        update_fields=[
            "status",
            "error_user_message",
            "error_system_message",
            "response_payload",
        ]
    )
    Guest.objects.filter(pk=guest.pk).update(evisitor_status=EvisitorGuestStatus.FAILED)


def submit_guest_checkout(
    guest: Guest,
    *,
    client: EvisitorClient | None = None,
    config=None,
) -> EvisitorSubmission:
    if config is None:
        config = _resolve_for_guest(guest)
    guest = Guest.objects.select_related("reservation").get(pk=guest.pk)

    if guest.evisitor_status == EvisitorGuestStatus.CHECKED_OUT:
        return (
            EvisitorSubmission.objects.filter(
                guest=guest, status=EvisitorGuestStatus.CHECKED_OUT
            )
            .order_by("-created_at")
            .first()
        )

    payload = build_check_out_payload(guest, config=config)
    masked = mask_payload_for_log(payload)
    registration_id = guest.evisitor_registration_id

    submission = EvisitorSubmission.objects.create(
        tenant=guest.tenant,
        guest=guest,
        registration_id=registration_id,
        status=EvisitorGuestStatus.PENDING,
        request_payload=masked,
        created_at=timezone.now(),
    )

    own_client = client is None
    if own_client:
        client = EvisitorClient(config)
    assert client is not None

    try:
        if own_client:
            client.login()
        client.execute_action("CheckOutTourist", payload)
    except (EvisitorApiError, EvisitorValidationError, EvisitorConfigError) as exc:
        _record_checkout_failure(submission, guest, exc)
        raise
    finally:
        if own_client:
            try:
                client.logout()
            finally:
                client.close()

    now = timezone.now()
    submission.status = EvisitorGuestStatus.CHECKED_OUT
    submission.submitted_at = now
    submission.response_payload = {"ok": True, "action": "CheckOutTourist"}
    submission.save(update_fields=["status", "submitted_at", "response_payload"])

    Guest.objects.filter(pk=guest.pk).update(
        evisitor_status=EvisitorGuestStatus.CHECKED_OUT,
    )
    return submission


def checkout_reservation_guests_in_evisitor(reservation) -> list[EvisitorSubmission]:
    """Odjavi sve goste rezervacije koji su u eVisitoru prijavljeni (status sent)."""
    guests = list(
        Guest.objects.filter(
            reservation_id=reservation.pk,
            evisitor_status=EvisitorGuestStatus.SENT,
        ).select_related("reservation", "reservation__property", "tenant")
    )
    if not guests:
        return []

    try:
        config = resolve_evisitor_config(reservation.tenant, reservation.property)
    except EvisitorConfigError:
        Guest.objects.filter(pk__in=[g.pk for g in guests]).update(
            evisitor_status=EvisitorGuestStatus.CHECKED_OUT,
        )
        return []

    submissions: list[EvisitorSubmission] = []
    client = EvisitorClient(config)
    try:
        client.login()
        for guest in guests:
            submissions.append(submit_guest_checkout(guest, client=client, config=config))
    finally:
        try:
            client.logout()
        finally:
            client.close()
    return submissions
