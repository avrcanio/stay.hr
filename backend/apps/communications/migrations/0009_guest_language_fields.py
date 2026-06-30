from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0008_guestinboundmessage_imap_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="guestmessagethreadstate",
            name="conversation_language",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="guestmessagethreadstate",
            name="conversation_language_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("override", "Override"),
                    ("reply_language", "Reply language"),
                    ("message", "Message"),
                    ("conversation", "Conversation"),
                    ("country", "Country"),
                    ("tenant_default", "Tenant default"),
                    ("fallback", "Fallback"),
                ],
                default="",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="guestmessagethreadstate",
            name="conversation_language_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="guestmessagedraft",
            name="language_source",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="guestmessagedraft",
            name="language_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
