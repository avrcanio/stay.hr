# Migration A — nullable fields only (zero-downtime step 1)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0009_guest_language_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="guestoutboundmessage",
            name="provider",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Message provider, e.g. meta, 360dialog.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="guestoutboundmessage",
            name="provider_message_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Provider message ID, e.g. Meta wamid.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="guestoutboundmessage",
            name="delivery_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("sent", "Sent"),
                    ("delivered", "Delivered"),
                    ("read", "Read"),
                    ("failed", "Failed"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="guestoutboundmessage",
            name="retry_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="guestoutboundmessage",
            name="next_retry_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="guestoutboundmessage",
            name="status",
            field=models.CharField(
                choices=[
                    ("handoff_whatsapp", "WhatsApp handoff"),
                    ("queued", "Queued"),
                    ("pending_send", "Pending send"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="guestoutboundmessage",
            index=models.Index(
                fields=["provider", "provider_message_id"],
                name="communicati_provide_8a1f2c_idx",
            ),
        ),
    ]
