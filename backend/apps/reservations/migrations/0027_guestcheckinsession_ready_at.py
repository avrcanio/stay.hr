from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0026_documentintakejob_web_guest"),
    ]

    operations = [
        migrations.AddField(
            model_name="guestcheckinsession",
            name="ready_at",
            field=models.DateTimeField(
                blank=True,
                help_text="First time all required slots became ready (analytics; set once).",
                null=True,
            ),
        ),
    ]
