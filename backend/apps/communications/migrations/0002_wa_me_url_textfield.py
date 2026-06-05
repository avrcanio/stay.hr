from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0001_guest_message_models"),
    ]

    operations = [
        migrations.AlterField(
            model_name="guestoutboundmessage",
            name="wa_me_url",
            field=models.TextField(blank=True, default=""),
        ),
    ]
