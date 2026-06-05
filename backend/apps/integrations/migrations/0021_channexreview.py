from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0020_alter_channelrateplan_options"),
        ("reservations", "0007_reservation_channel_timestamps"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChannexReview",
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
                ("channex_review_id", models.CharField(max_length=128, unique=True)),
                ("channex_booking_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("ota", models.CharField(blank=True, db_index=True, max_length=32)),
                ("ota_reservation_id", models.CharField(blank=True, max_length=64)),
                ("ota_review_id", models.CharField(blank=True, max_length=128)),
                ("guest_name", models.CharField(blank=True, max_length=255)),
                ("content", models.TextField(blank=True)),
                ("reply", models.TextField(blank=True)),
                (
                    "overall_score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                    ),
                ),
                ("scores", models.JSONField(blank=True, default=list)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("is_replied", models.BooleanField(default=False)),
                ("is_hidden", models.BooleanField(default=False)),
                ("expired_at", models.DateTimeField(blank=True, null=True)),
                ("received_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("reply_sent_at", models.DateTimeField(blank=True, null=True)),
                ("reply_scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "integration",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="channex_reviews",
                        to="integrations.integrationconfig",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="channex_reviews",
                        to="reservations.reservation",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)ss",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["-received_at", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="channexreview",
            index=models.Index(fields=["tenant", "received_at"], name="integration_tenant__chn_rev_idx"),
        ),
        migrations.AddIndex(
            model_name="channexreview",
            index=models.Index(
                fields=["tenant", "reservation"],
                name="integration_tenant__chn_rev_res_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="channexreview",
            index=models.Index(
                fields=["tenant", "is_replied", "received_at"],
                name="integration_tenant__chn_rev_unr_idx",
            ),
        ),
    ]
