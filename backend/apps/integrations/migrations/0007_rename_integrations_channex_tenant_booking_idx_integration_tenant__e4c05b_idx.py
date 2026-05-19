from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0006_channexbookingrevision"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="channexbookingrevision",
            new_name="integration_tenant__e4c05b_idx",
            old_name="integrations_channex_tenant_booking_idx",
        ),
    ]
