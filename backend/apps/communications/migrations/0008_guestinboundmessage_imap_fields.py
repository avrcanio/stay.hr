from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0007_guestoutboundmessage_media_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="guestinboundmessage",
            name="message_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="guestinboundmessage",
            name="raw_from",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="guestinboundmessage",
            name="received_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="guestinboundmessage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("message_id__gt", "")),
                fields=("tenant", "message_id"),
                name="guestinboundmessage_unique_message_id_per_tenant",
            ),
        ),
    ]
