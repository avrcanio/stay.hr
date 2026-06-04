from __future__ import annotations

import logging

from celery import shared_task

from apps.core.timezone import property_local_now, tenant_local_now
from apps.integrations.evisitor.exceptions import (
    EvisitorApiError,
    EvisitorConfigError,
    EvisitorValidationError,
)
from apps.integrations.evisitor.summary import evisitor_summary_for_guests
from apps.reservations.checkout import CheckoutBlockedError, perform_reservation_checkout
from apps.reservations.guest_slots import guests_for_checkout
from apps.reservations.models import Reservation
from apps.tenants.models import TenantReceptionSettings

logger = logging.getLogger(__name__)

__all__ = ["run_auto_checkouts", "tenant_local_now", "property_local_now"]


def _skip_reason_for_summary(summary: str) -> str:
    if summary == "none":
        return "evisitor_none"
    return "evisitor_incomplete"


def _skipped_entry(reservation: Reservation, reason: str) -> dict:
    return {
        "reservation_id": reservation.pk,
        "booking_code": reservation.booking_code or str(reservation.pk),
        "reason": reason,
    }


def _is_due_for_auto_checkout(reservation: Reservation) -> bool:
    prop = reservation.property
    now = property_local_now(prop)
    if now.date() != reservation.check_out:
        return False
    return now.time() >= prop.check_out_time


@shared_task
def run_auto_checkouts() -> dict:
    from apps.core.tasks import (
        notify_auto_checkout_summary,
        notify_reservation_status_changed,
    )

    result: dict = {
        "tenants_processed": 0,
        "checked_out": 0,
        "skipped": 0,
    }

    settings_list = TenantReceptionSettings.objects.filter(
        auto_checkout_enabled=True,
    ).select_related("tenant")

    for settings in settings_list:
        tenant = settings.tenant
        skipped: list[dict] = []
        tenant_active = False

        reservations = (
            Reservation.objects.filter(
                tenant=tenant,
                status=Reservation.Status.CHECKED_IN,
            )
            .select_related("property", "tenant")
            .prefetch_related("guests")
        )

        for reservation in reservations:
            if not _is_due_for_auto_checkout(reservation):
                continue

            tenant_active = True
            summary = evisitor_summary_for_guests(
                guests_for_checkout(reservation),
                reference_date=reservation.check_in,
            )
            if summary != "complete":
                skipped.append(
                    _skipped_entry(reservation, _skip_reason_for_summary(summary))
                )
                continue

            try:
                old_status = reservation.status
                perform_reservation_checkout(reservation, source="auto")
            except CheckoutBlockedError as exc:
                skipped.append(_skipped_entry(reservation, exc.code))
                continue
            except EvisitorValidationError as exc:
                logger.warning(
                    "Auto checkout eVisitor validation failed reservation_id=%s: %s",
                    reservation.pk,
                    exc,
                )
                skipped.append(_skipped_entry(reservation, "evisitor_validation_error"))
                continue
            except (EvisitorApiError, EvisitorConfigError) as exc:
                logger.warning(
                    "Auto checkout eVisitor API failed reservation_id=%s: %s",
                    reservation.pk,
                    exc,
                )
                skipped.append(_skipped_entry(reservation, "evisitor_api_error"))
                continue

            notify_reservation_status_changed.delay(
                reservation.pk,
                old_status,
                Reservation.Status.CHECKED_OUT,
            )
            result["checked_out"] += 1

        if tenant_active:
            result["tenants_processed"] += 1

        if skipped:
            notify_auto_checkout_summary.delay(tenant.pk, skipped)
            result["skipped"] += len(skipped)

    return result
