from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0011_remove_smoobu"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reservation",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("expected", "Expected"),
                    ("checked_in", "Checked in"),
                    ("checked_out", "Checked out"),
                    ("canceled", "Canceled"),
                    ("no_show", "No show"),
                    ("refused", "Refused"),
                ],
                default="expected",
                max_length=32,
            ),
        ),
    ]
