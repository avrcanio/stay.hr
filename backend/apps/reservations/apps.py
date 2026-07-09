from django.apps import AppConfig


class ReservationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reservations"
    verbose_name = "Reservations"

    def ready(self) -> None:
        from apps.reservations import signals  # noqa: F401
        from apps.reservations import booking_payout_admin  # noqa: F401
        from apps.reservations import guest_checkin_events  # noqa: F401
