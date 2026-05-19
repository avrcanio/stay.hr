import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0002_apiapplication_token_encrypted"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantMembership",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tenant_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["tenant__name", "user__username"],
            },
        ),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.UniqueConstraint(
                fields=("user", "tenant"),
                name="tenants_membership_unique_user_tenant",
            ),
        ),
    ]
