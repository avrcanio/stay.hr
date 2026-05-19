from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.reservations.models import Reservation


@receiver(post_save, sender=Reservation)
def reservation_created_notify(sender, instance: Reservation, created: bool, **kwargs):
    if not created:
        return
    if instance.status == Reservation.Status.CANCELED:
        return

    from apps.core.tasks import notify_new_reservation

    notify_new_reservation.delay(instance.pk)
