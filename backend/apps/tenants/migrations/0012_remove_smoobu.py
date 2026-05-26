from django.db import migrations, models


def migrate_channel_manager_forward(apps, schema_editor):
    TenantReceptionSettings = apps.get_model("tenants", "TenantReceptionSettings")
    TenantReceptionSettings.objects.filter(channel_manager="smoobu").update(
        channel_manager="channex"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0011_staff_login_event"),
    ]

    operations = [
        migrations.RunPython(migrate_channel_manager_forward, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tenantreceptionsettings",
            name="channel_manager",
            field=models.CharField(
                choices=[("none", "Manual"), ("channex", "Channex")],
                default="none",
                help_text="Outbound channel connector for this tenant (Channex or manual).",
                max_length=16,
            ),
        ),
    ]
