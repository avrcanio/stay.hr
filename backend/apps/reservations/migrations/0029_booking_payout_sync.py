import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """No-op: columns were applied via 0026_booking_payout_sync / 0028_booking_payout_import."""

    dependencies = [
        ("reservations", "0028_booking_payout_import"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = []
