from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_invoice_buyer_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="buyer_country",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
