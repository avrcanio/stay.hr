from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.reservations.models import Reservation


@receiver(post_save, sender=Reservation)
def reservation_created_notify(sender, instance: Reservation, created: bool, **kwargs):
    if not created:
        return
    if instance.status == Reservation.Status.CANCELED:
        return

    from apps.reservations.booking_lifecycle import is_web_pending_booking

    # Web bookings: push after Smoobu confirms (see booking_lifecycle.confirm_web_booking).
    if is_web_pending_booking(instance):
        return

    from apps.core.tasks import notify_new_reservation

    notify_new_reservation.delay(instance.pk)


@receiver(post_save, sender=Reservation)
def reservation_smoobu_block_on_create(sender, instance: Reservation, created: bool, **kwargs):
    if not created:
        return
    if instance.status == Reservation.Status.CANCELED:
        return

    from apps.integrations.smoobu.tasks import sync_reservation_smoobu_blocks_task

    transaction.on_commit(
        lambda reservation_id=instance.pk: sync_reservation_smoobu_blocks_task.delay(
            reservation_id,
            "sync",
        )
    )
