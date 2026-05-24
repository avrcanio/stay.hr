from django.db import migrations


def set_demo_inventory_ari(apps, schema_editor):
    from apps.integrations.models import IntegrationConfig
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(slug="demo").first()
    if tenant is None:
        return

    for row in IntegrationConfig.objects.filter(
        tenant=tenant,
        provider=IntegrationConfig.Provider.CHANNEX,
        is_active=True,
    ):
        config = row.get_config_dict()
        if config.get("use_generated_ari") is False:
            continue
        config["use_generated_ari"] = False
        row.set_config_dict(config)
        row.save(update_fields=["config_encrypted", "config", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0015_whatsapp_index_fix"),
    ]

    operations = [
        migrations.RunPython(set_demo_inventory_ari, migrations.RunPython.noop),
    ]
