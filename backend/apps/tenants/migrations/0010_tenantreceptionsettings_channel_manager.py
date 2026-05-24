from django.db import migrations, models


def seed_channel_manager(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    TenantReceptionSettings = apps.get_model("tenants", "TenantReceptionSettings")

    slug_to_manager = {
        "demo": "channex",
        "uzorita": "smoobu",
    }

    for tenant in Tenant.objects.all():
        manager = slug_to_manager.get(tenant.slug, "none")
        settings_row, _ = TenantReceptionSettings.objects.get_or_create(
            tenant=tenant,
            defaults={"channel_manager": manager},
        )
        if settings_row.channel_manager != manager:
            settings_row.channel_manager = manager
            settings_row.save(update_fields=["channel_manager", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0009_tenantreceptionsettings_guest_smtp_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantreceptionsettings",
            name="channel_manager",
            field=models.CharField(
                choices=[
                    ("none", "Manual"),
                    ("smoobu", "Smoobu"),
                    ("channex", "Channex"),
                ],
                default="none",
                help_text="Outbound channel connector for this tenant (Smoobu, Channex, or manual).",
                max_length=16,
            ),
        ),
        migrations.RunPython(seed_channel_manager, migrations.RunPython.noop),
    ]
