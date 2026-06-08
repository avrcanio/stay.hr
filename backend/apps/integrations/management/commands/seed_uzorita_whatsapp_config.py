import os

from django.core.management.base import BaseCommand

from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.config import (
    d360_api_base_url_from_env,
    d360_api_key_from_env,
    is_360dialog_provider,
    provider_from_env,
)
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Create or update WhatsApp IntegrationConfig for tenant uzorita "
        "(Meta Graph API or 360dialog Direct API)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument(
            "--provider",
            default="",
            help="meta or 360dialog (or WHATSAPP_PROVIDER env).",
        )
        parser.add_argument(
            "--phone-number-id",
            default="",
            help="Meta Phone Number ID / 360dialog channel external ID "
            "(or WHATSAPP_PHONE_NUMBER_ID env).",
        )
        parser.add_argument(
            "--display-phone-number",
            default="",
            help="Display number e.g. +385... (or WHATSAPP_DISPLAY_PHONE_NUMBER env).",
        )
        parser.add_argument(
            "--waba-id",
            default="",
            help="WhatsApp Business Account ID (or WHATSAPP_WABA_ID env).",
        )
        parser.add_argument(
            "--access-token",
            default="",
            help="Meta Graph API token (or WHATSAPP_ACCESS_TOKEN env). Never commit.",
        )
        parser.add_argument(
            "--d360-api-key",
            default="",
            help="360dialog API key (or D360_API_KEY env). Never commit.",
        )
        parser.add_argument(
            "--d360-api-base-url",
            default="",
            help="360dialog API base URL (or D360_API_BASE_URL env).",
        )
        parser.add_argument(
            "--auto-reply",
            default="false",
            help="Enable inbound auto-reply (true/false). Default false for stateful autocheck-in flow.",
        )

    def handle(self, *args, **options):
        provider = (
            options["provider"] or os.getenv("WHATSAPP_PROVIDER", "meta")
        ).strip().lower()
        phone_number_id = (
            options["phone_number_id"] or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        ).strip()
        display_phone_number = (
            options["display_phone_number"]
            or os.getenv("WHATSAPP_DISPLAY_PHONE_NUMBER", "")
        ).strip()
        waba_id = (options["waba_id"] or os.getenv("WHATSAPP_WABA_ID", "")).strip()

        if is_360dialog_provider(provider):
            access_token = (
                options["d360_api_key"]
                or options["access_token"]
                or d360_api_key_from_env()
            ).strip()
            api_base_url = (
                options["d360_api_base_url"] or d360_api_base_url_from_env()
            ).strip()
            if not access_token:
                self.stderr.write(
                    self.style.ERROR(
                        "360dialog: D360_API_KEY je obavezan.\n"
                        "  export D360_API_KEY='...'\n"
                        "  docker compose exec django python manage.py seed_uzorita_whatsapp_config"
                    )
                )
                return
        else:
            access_token = (
                options["access_token"] or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
            ).strip()
            api_base_url = ""
            if not phone_number_id or not access_token:
                self.stderr.write(
                    self.style.ERROR(
                        "Meta: WHATSAPP_PHONE_NUMBER_ID i WHATSAPP_ACCESS_TOKEN su obavezni.\n"
                        "  export WHATSAPP_PHONE_NUMBER_ID='...'\n"
                        "  export WHATSAPP_ACCESS_TOKEN='...'\n"
                        "  docker compose exec django python manage.py seed_uzorita_whatsapp_config"
                    )
                )
                return

        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {options['tenant_slug']}"))
            return

        auto_reply_raw = str(options["auto_reply"] or "false").strip().lower()
        auto_reply = auto_reply_raw not in ("0", "false", "no", "off")

        config = {
            "provider": provider,
            "phone_number_id": phone_number_id,
            "display_phone_number": display_phone_number,
            "waba_id": waba_id,
            "access_token": access_token,
            "auto_reply": auto_reply,
            "whatsapp_templates": {
                "header_image_url": "https://stay.hr/static/whatsapp-header.png",
                "welcome": {
                    "hr": "stay_welcome_hr",
                    "en": "stay_welcome_en",
                    "de": "stay_welcome_de",
                    "es": "stay_welcome_es",
                    "fr": "stay_welcome_fr",
                },
            },
        }
        if api_base_url:
            config["api_base_url"] = api_base_url

        routing_key = phone_number_id or display_phone_number.replace("+", "").strip()
        if not routing_key:
            self.stderr.write(
                self.style.ERROR(
                    "routing_key missing: set WHATSAPP_PHONE_NUMBER_ID or display phone."
                )
            )
            return

        row, created = IntegrationConfig.objects.update_or_create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            property=None,
            defaults={
                "is_active": True,
                "routing_key": routing_key,
            },
        )
        row.routing_key = routing_key
        row.set_config_dict(config)
        row.save(
            update_fields=[
                "routing_key",
                "config_encrypted",
                "config",
                "is_active",
                "updated_at",
            ]
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} WhatsApp IntegrationConfig id={row.pk} "
                f"(tenant={tenant.slug}, provider={provider}, routing_key={routing_key})."
            )
        )
