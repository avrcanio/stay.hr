from django.conf import settings
from django.db import migrations, models


def create_staff_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    StaffProfile = apps.get_model("tenants", "StaffProfile")
    for user in User.objects.filter(is_staff=True):
        StaffProfile.objects.get_or_create(
            user_id=user.pk,
            defaults={"preferred_language": "hr"},
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0006_tenantdomain_property"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "preferred_language",
                    models.CharField(
                        choices=[
                            ("hr", "hr"),
                            ("en", "en"),
                            ("es", "es"),
                            ("fr", "fr"),
                            ("de", "de"),
                            ("it", "it"),
                        ],
                        default="hr",
                        max_length=10,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="staff_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Staff profile",
                "verbose_name_plural": "Staff profiles",
            },
        ),
        migrations.RunPython(create_staff_profiles, migrations.RunPython.noop),
    ]
