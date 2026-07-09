from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0025_guestcheckinsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentintakejob",
            name="guest_checkin_slot_position",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="documentintakejob",
            name="source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("hospira_batch", "Hospira batch"),
                    ("whatsapp", "WhatsApp"),
                    ("whatsapp_operator", "WhatsApp operator"),
                    ("web_guest", "Web guest check-in"),
                ],
                default="",
                max_length=32,
            ),
        ),
    ]
