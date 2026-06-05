from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0002_wa_me_url_textfield"),
    ]

    operations = [
        migrations.AlterField(
            model_name="guestmessagedraft",
            name="channel",
            field=models.CharField(
                blank=True,
                choices=[
                    ("email", "Email"),
                    ("whatsapp", "WhatsApp"),
                    ("booking", "Booking.com"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="guestoutboundmessage",
            name="channel",
            field=models.CharField(
                choices=[
                    ("email", "Email"),
                    ("whatsapp", "WhatsApp"),
                    ("booking", "Booking.com"),
                ],
                max_length=16,
            ),
        ),
    ]
