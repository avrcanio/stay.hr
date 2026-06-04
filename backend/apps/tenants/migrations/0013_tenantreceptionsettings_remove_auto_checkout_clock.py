from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0012_remove_smoobu"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="tenantreceptionsettings",
            name="auto_checkout_last_run_date",
        ),
        migrations.RemoveField(
            model_name="tenantreceptionsettings",
            name="auto_checkout_time",
        ),
    ]
