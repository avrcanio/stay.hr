from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0008_channex_ari_models"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integrationconfig",
            name="provider",
            field=models.CharField(
                choices=[
                    ("booking", "Booking"),
                    ("email", "Email"),
                    ("ical", "iCal"),
                    ("evisitor", "eVisitor"),
                    ("channex", "Channex"),
                    ("smoobu", "Smoobu"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
    ]
