import json

from django.conf import settings
from django.db import migrations, models


def _decrypt_config(encrypted: str) -> dict:
    if not encrypted:
        return {}
    try:
        from cryptography.fernet import Fernet

        key = getattr(settings, "STAY_INTEGRATION_FERNET_KEY", "") or ""
        if not key:
            return {}
        f = Fernet(key.encode() if isinstance(key, str) else key)
        raw = f.decrypt(encrypted.encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _encrypt_config(data: dict) -> str:
    from cryptography.fernet import Fernet

    key = getattr(settings, "STAY_INTEGRATION_FERNET_KEY", "") or ""
    if not key:
        return ""
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return f.encrypt(json.dumps(data).encode("utf-8")).decode("utf-8")


def strip_whatsapp_legacy_config(apps, schema_editor):
    IntegrationConfig = apps.get_model("integrations", "IntegrationConfig")
    for row in IntegrationConfig.objects.filter(provider="whatsapp"):
        config = dict(row.config or {})
        if row.config_encrypted:
            config.update(_decrypt_config(row.config_encrypted))
        changed = False
        for legacy_key in ("access_token", "provider", "api_base_url"):
            if legacy_key in config:
                config.pop(legacy_key, None)
                changed = True
        phone_number_id = str(config.get("phone_number_id") or "").strip()
        if phone_number_id and row.routing_key != phone_number_id:
            row.routing_key = phone_number_id
            changed = True
        if changed:
            row.config = {}
            row.config_encrypted = _encrypt_config(config) if config else ""
            row.save(update_fields=["routing_key", "config", "config_encrypted", "updated_at"])


def deactivate_duplicate_platform_routing_keys(apps, schema_editor):
    IntegrationConfig = apps.get_model("integrations", "IntegrationConfig")
    Tenant = apps.get_model("tenants", "Tenant")
    platform = Tenant.objects.filter(slug="platform", is_system=True).first()
    if platform is None:
        return
    platform_rows = IntegrationConfig.objects.filter(
        tenant=platform,
        provider="whatsapp",
        is_active=True,
    )
    for platform_row in platform_rows:
        IntegrationConfig.objects.filter(
            provider="whatsapp",
            routing_key=platform_row.routing_key,
            is_active=True,
        ).exclude(pk=platform_row.pk).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0025_channexbookingrevision_nullable_reservation"),
        ("tenants", "0016_tenant_is_system"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationconfig",
            name="is_platform_default",
            field=models.BooleanField(
                default=False,
                help_text="Default platform WhatsApp config (at most one active per provider).",
            ),
        ),
        migrations.CreateModel(
            name="WhatsAppInboundRouting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("routed", "Routed"), ("ambiguous", "Ambiguous"), ("unrouted", "Unrouted"), ("failed", "Failed"), ("dismissed", "Dismissed")], db_index=True, default="pending", max_length=16)),
                ("routing_method", models.CharField(blank=True, choices=[("thread", "Thread"), ("booking_code", "Booking code"), ("phone", "Phone"), ("manual", "Manual"), ("", "—")], default="", max_length=16)),
                ("candidate_reservations", models.JSONField(blank=True, default=list)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("message", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="inbound_routing", to="integrations.whatsappmessage")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="whatsapp_inbound_routings_resolved", to=settings.AUTH_USER_MODEL)),
                ("resolved_reservation", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="whatsapp_inbound_routings", to="reservations.reservation")),
                ("resolved_tenant", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="whatsapp_inbound_routings", to="tenants.tenant")),
                ("tenant", models.ForeignKey(on_delete=models.deletion.CASCADE, to="tenants.tenant")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="whatsappinboundrouting",
            index=models.Index(fields=["tenant", "status", "created_at"], name="integration_tenant__wa_route_idx"),
        ),
        migrations.AddConstraint(
            model_name="integrationconfig",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True), ("is_platform_default", True), ("provider", "whatsapp")),
                fields=("provider",),
                name="integrations_config_unique_active_platform_whatsapp",
            ),
        ),
        migrations.RunPython(strip_whatsapp_legacy_config, migrations.RunPython.noop),
        migrations.RunPython(deactivate_duplicate_platform_routing_keys, migrations.RunPython.noop),
    ]
