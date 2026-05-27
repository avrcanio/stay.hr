from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_backfill_tenant_fiscal_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="buyer_address",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="invoice",
            name="buyer_document_number",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
