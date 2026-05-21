from datetime import time

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0004_apiapplication_fcm_token"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantReceptionSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("auto_checkout_enabled", models.BooleanField(default=False)),
                (
                    "auto_checkout_time",
                    models.TimeField(default=time(10, 0)),
                ),
                (
                    "auto_checkout_last_run_date",
                    models.DateField(blank=True, null=True),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reception_settings",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Tenant reception settings",
            },
        ),
    ]
