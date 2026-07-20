import os

from django.core.management.base import BaseCommand

from apps.integrations.models import IntegrationConfig
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Create or update WhatsApp IntegrationConfig for a hotel tenant "
        "(Meta WhatsApp Cloud API only)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument(
            "--phone-number-id",
            default="",
            help="Meta phone_number_id (or WHATSAPP_PHONE_NUMBER_ID env).",
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
            "--auto-reply",
            default="false",
            help="Enable inbound auto-reply (true/false). Default false for stateful autocheck-in flow.",
        )

    def handle(self, *args, **options):
        phone_number_id = (
            options["phone_number_id"] or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        ).strip()
        display_phone_number = (
            options["display_phone_number"]
            or os.getenv("WHATSAPP_DISPLAY_PHONE_NUMBER", "")
        ).strip()
        waba_id = (options["waba_id"] or os.getenv("WHATSAPP_WABA_ID", "")).strip()

        if not phone_number_id:
            self.stderr.write(
                self.style.ERROR(
                    "phone_number_id is required.\n"
                    "  export WHATSAPP_PHONE_NUMBER_ID='...'\n"
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
            "phone_number_id": phone_number_id,
            "display_phone_number": display_phone_number,
            "waba_id": waba_id,
            "auto_reply": auto_reply,
            "whatsapp_templates": {
                "header_image_url": "https://stay.hr/static/whatsapp-header.png",
                "welcome": {
                    "hr": "stay_welcome_hr",
                    "en": "stay_welcome_en",
                    "de": "stay_welcome_de",
                    "es": "stay_welcome_es",
                    "fr": "stay_welcome_fr",
                    "it": "stay_welcome_it",
                },
            },
        }

        row, created = IntegrationConfig.objects.update_or_create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            property=None,
            defaults={
                "is_active": True,
                "routing_key": phone_number_id,
            },
        )
        row.routing_key = phone_number_id
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
                f"(tenant={tenant.slug}, routing_key={phone_number_id}). "
                f"Access token: WHATSAPP_ACCESS_TOKEN in .env."
            )
        )
