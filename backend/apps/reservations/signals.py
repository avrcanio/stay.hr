from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.reservations.models import Reservation


@receiver(post_save, sender=Reservation)
def reservation_created_notify(sender, instance: Reservation, created: bool, **kwargs):
    if not created:
        return
    if instance.status == Reservation.Status.CANCELED:
        return

    from apps.reservations.booking_lifecycle import is_web_pending_booking

    # Web bookings: push after channel manager confirms (see booking_lifecycle.confirm_web_booking).
    if is_web_pending_booking(instance):
        return

    from apps.core.tasks import notify_new_reservation

    notify_new_reservation.delay(instance.pk)


@receiver(post_save, sender=Reservation)
def reservation_outbound_on_create(sender, instance: Reservation, created: bool, **kwargs):
    if not created:
        return
    if instance.status == Reservation.Status.CANCELED:
        return

    from apps.integrations.channel_manager.tasks import sync_reservation_outbound_task

    transaction.on_commit(
        lambda reservation_id=instance.pk: sync_reservation_outbound_task.delay(
            reservation_id,
            "sync",
        )
    )


@receiver(pre_save, sender=Reservation)
def reservation_snapshot_before_save(sender, instance: Reservation, **kwargs):
    if not instance.pk:
        instance._channel_sync_snapshot = None
        return
    try:
        old = Reservation.objects.get(pk=instance.pk)
    except Reservation.DoesNotExist:
        instance._channel_sync_snapshot = None
        return
    instance._channel_sync_snapshot = {
        "check_in": old.check_in,
        "check_out": old.check_out,
        "status": old.status,
    }


@receiver(post_save, sender=Reservation)
def reservation_outbound_on_update(sender, instance: Reservation, created: bool, **kwargs):
    if created:
        return

    snapshot = getattr(instance, "_channel_sync_snapshot", None)
    if not snapshot:
        return

    from apps.integrations.channel_manager.tasks import sync_reservation_outbound_task

    old_check_in = snapshot["check_in"]
    old_check_out = snapshot["check_out"]
    old_status = snapshot["status"]

    dates_changed = old_check_in != instance.check_in or old_check_out != instance.check_out
    status_changed = old_status != instance.status

    if not dates_changed and not status_changed:
        return

    def queue_updates():
        if instance.status == Reservation.Status.CANCELED:
            sync_reservation_outbound_task.delay(instance.pk, "remove")
            return

        if status_changed and instance.status in {
            Reservation.Status.PENDING,
            Reservation.Status.EXPECTED,
            Reservation.Status.CHECKED_IN,
        }:
            sync_reservation_outbound_task.delay(instance.pk, "sync")
            return

        if dates_changed:
            from apps.integrations.channel_manager.resolver import get_channel_manager
            from apps.integrations.channex.reservation_availability_service import (
                sync_reservation_channex_availability_for_dates,
            )
            from apps.tenants.models import ChannelManager

            if get_channel_manager(instance.tenant) == ChannelManager.CHANNEX:
                sync_reservation_channex_availability_for_dates(
                    instance, old_check_in, old_check_out
                )
            sync_reservation_outbound_task.delay(instance.pk, "sync")

    transaction.on_commit(queue_updates)
