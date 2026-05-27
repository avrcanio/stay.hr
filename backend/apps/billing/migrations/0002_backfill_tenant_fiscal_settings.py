from django.db import migrations


def create_fiscal_settings_for_tenants(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    TenantFiscalSettings = apps.get_model("billing", "TenantFiscalSettings")
    for tenant in Tenant.objects.all().iterator():
        TenantFiscalSettings.objects.get_or_create(tenant=tenant)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_fiscal_settings_for_tenants, migrations.RunPython.noop),
    ]
