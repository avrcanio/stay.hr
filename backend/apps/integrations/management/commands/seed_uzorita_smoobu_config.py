import os

from django.core.management.base import BaseCommand

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.mapping import (
    SMOOBU_API_BASE,
    UZORITA_SETTINGS_CHANNEL_ID,
    apartments_config_payload,
)
from apps.integrations.smoobu.verify import SmoobuKeyVerificationError, verify_smoobu_api_key
from apps.properties.models import Property
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Create or update Smoobu IntegrationConfig for tenant uzorita "
        "(encrypted api_key + apartment map). Requires a rotated API key."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument("--property-slug", default="uzorita")
        parser.add_argument(
            "--api-key",
            default="",
            help="Rotated Smoobu API key (or set SMOOBU_API_KEY env). Never commit.",
        )
        parser.add_argument(
            "--skip-verify",
            action="store_true",
            help="Store key without calling Smoobu GET /api/me (not recommended).",
        )

    def handle(self, *args, **options):
        api_key = (options["api_key"] or os.getenv("SMOOBU_API_KEY", "")).strip()
        if not api_key:
            self.stderr.write(
                self.style.ERROR(
                    "SMOOBU_API_KEY nije postavljen. "
                    "Rotirajte ključ u Smoobu Advanced → API Keys, zatim:\n"
                    "  export SMOOBU_API_KEY='...'\n"
                    "  docker compose exec django python manage.py seed_uzorita_smoobu_config"
                )
            )
            return

        if not options["skip_verify"]:
            try:
                profile = verify_smoobu_api_key(api_key)
            except SmoobuKeyVerificationError as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                return
            self.stdout.write(
                f"Smoobu API ključ OK (user id={profile.get('id')}, "
                f"email={profile.get('email', '?')})."
            )

        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {options['tenant_slug']}"))
            return

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()

        config = {
            "api_base": SMOOBU_API_BASE,
            "api_key": api_key,
            "settings_channel_id": UZORITA_SETTINGS_CHANNEL_ID,
            "apartments": apartments_config_payload(),
            "push_rates_enabled": True,
            "default_channel_id_for_create": 70,
        }

        row, created = IntegrationConfig.objects.update_or_create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.SMOOBU,
            property=prop,
            defaults={"is_active": True},
        )
        row.set_config_dict(config)
        row.save(update_fields=["config_encrypted", "config", "is_active", "updated_at"])

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} Smoobu IntegrationConfig id={row.pk} "
                f"(tenant={tenant.slug}, property={prop.slug if prop else 'tenant-wide'})."
            )
        )
        self.stdout.write("Apartment mapping:")
        for apt in config["apartments"]:
            self.stdout.write(
                f"  {apt['unit_code']:3s} unit_id={apt.get('unit_id', '-'):>3} "
                f"→ Smoobu {apt['smoobu_apartment_id']}"
            )
        self.stdout.write(
            self.style.WARNING(
                "Stari (izloženi) Smoobu ključ opozovite u Smoobu UI ako još nije učinjeno."
            )
        )
