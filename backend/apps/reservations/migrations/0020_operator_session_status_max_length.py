from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0019_reservation_whatsapp_autocheckin_waived_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="whatsappoperatorsession",
            name="status",
            field=models.CharField(
                choices=[
                    ("collecting", "Collecting"),
                    ("awaiting_confirm", "Awaiting confirm"),
                    ("awaiting_res_pick", "Awaiting reservation pick"),
                    ("processing", "Processing"),
                    ("done", "Done"),
                    ("failed", "Failed"),
                ],
                default="collecting",
                max_length=24,
            ),
        ),
    ]
