from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0004_alter_integrationconfig_options_and_more"),
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
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
    ]
