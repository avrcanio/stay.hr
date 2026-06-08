from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0013_tenantreceptionsettings_remove_auto_checkout_clock"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantreceptionsettings",
            name="whatsapp_operator_phones",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='WhatsApp operator whitelist, e.g. [{"name": "Toni", "phone": "+385..."}].',
            ),
        ),
    ]
