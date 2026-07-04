from django.db import migrations, models


def create_platform_tenant(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Tenant.objects.get_or_create(
        slug="platform",
        defaults={
            "name": "Stay.hr Platform",
            "status": "active",
            "is_system": True,
            "timezone": "Europe/Zagreb",
            "default_language": "hr",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0015_tenantreceptionsettings_guest_imap"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="is_system",
            field=models.BooleanField(
                default=False,
                help_text="System tenant (e.g. platform WhatsApp); hidden from default admin lists.",
            ),
        ),
        migrations.RunPython(create_platform_tenant, migrations.RunPython.noop),
    ]
