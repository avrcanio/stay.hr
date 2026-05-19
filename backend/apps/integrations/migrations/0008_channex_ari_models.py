import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0001_initial"),
        ("integrations", "0007_rename_integrations_channex_tenant_booking_idx_integration_tenant__e4c05b_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChannelRatePlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32)),
                ("title", models.CharField(blank=True, max_length=128)),
                ("channex_room_type_id", models.CharField(max_length=36)),
                ("channex_rate_plan_id", models.CharField(max_length=36)),
                ("default_rate", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("currency", models.CharField(default="GBP", max_length=3)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channel_rate_plans",
                        to="properties.property",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant"),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channel_rate_plans",
                        to="properties.unit",
                    ),
                ),
            ],
            options={
                "ordering": ["property_id", "unit_id", "code"],
            },
        ),
        migrations.CreateModel(
            name="ChannexAriOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[("availability", "Availability"), ("restrictions", "Rates & restrictions")],
                        max_length=16,
                    ),
                ),
                ("values", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("channex_task_ids", models.JSONField(blank=True, default=list)),
                ("error_message", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channex_ari_outbox",
                        to="properties.property",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant"),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="RatePlanDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("rate", models.DecimalField(decimal_places=2, max_digits=10)),
                ("min_stay_arrival", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("min_stay_through", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("max_stay", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("stop_sell", models.BooleanField(default=False)),
                ("closed_to_arrival", models.BooleanField(default=False)),
                ("closed_to_departure", models.BooleanField(default=False)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "rate_plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="days",
                        to="integrations.channelrateplan",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant"),
                ),
            ],
            options={
                "ordering": ["date", "rate_plan_id"],
            },
        ),
        migrations.CreateModel(
            name="UnitAvailabilityDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("availability", models.PositiveSmallIntegerField(default=1)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant"),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="availability_days",
                        to="properties.unit",
                    ),
                ),
            ],
            options={
                "ordering": ["date", "unit_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="channelrateplan",
            constraint=models.UniqueConstraint(
                fields=("tenant", "property", "unit", "code"),
                name="integrations_rateplan_unique_tenant_property_unit_code",
            ),
        ),
        migrations.AddConstraint(
            model_name="channelrateplan",
            constraint=models.UniqueConstraint(
                fields=("tenant", "channex_rate_plan_id"),
                name="integrations_rateplan_unique_tenant_channex_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="rateplanday",
            constraint=models.UniqueConstraint(
                fields=("tenant", "rate_plan", "date"),
                name="integrations_rateplanday_unique_tenant_plan_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="unitavailabilityday",
            constraint=models.UniqueConstraint(
                fields=("tenant", "unit", "date"),
                name="integrations_unitavail_unique_tenant_unit_date",
            ),
        ),
        migrations.AddIndex(
            model_name="channexarioutbox",
            index=models.Index(fields=["tenant", "property", "kind", "status"], name="integration_tenant__a8f1c2_idx"),
        ),
        migrations.AddIndex(
            model_name="rateplanday",
            index=models.Index(fields=["tenant", "rate_plan", "synced_at"], name="integration_tenant__b3e4d1_idx"),
        ),
        migrations.AddIndex(
            model_name="unitavailabilityday",
            index=models.Index(fields=["tenant", "unit", "synced_at"], name="integration_tenant__c5f6a7_idx"),
        ),
    ]
