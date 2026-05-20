import os

from django.core.management.base import BaseCommand

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.mapping import apartments_config_payload
from apps.integrations.smoobu.verify import SmoobuKeyVerificationError, verify_smoobu_api_key
from apps.properties.models import Property
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Store a rotated Smoobu API key in encrypted IntegrationConfig "
        "(verifies via GET /api/me). Run after revoking the old key in Smoobu UI."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument("--property-slug", default="uzorita")
        parser.add_argument(
            "--api-key",
            default="",
            help="New Smoobu API key (or SMOOBU_API_KEY env).",
        )
        parser.add_argument(
            "--skip-verify",
            action="store_true",
            help="Update encrypted key without Smoobu API check.",
        )

    def handle(self, *args, **options):
        api_key = (options["api_key"] or os.getenv("SMOOBU_API_KEY", "")).strip()
        if not api_key:
            self.stderr.write(
                self.style.ERROR(
                    "Postavite SMOOBU_API_KEY (rotirani ključ iz Smoobu Advanced → API Keys)."
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
                f"Verified Smoobu key for user id={profile.get('id')} "
                f"({profile.get('email', '?')})."
            )

        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {options['tenant_slug']}"))
            return

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        row = IntegrationConfig.objects.filter(
            tenant=tenant,
            provider=IntegrationConfig.Provider.SMOOBU,
            property=prop,
        ).first()

        if row is None:
            self.stdout.write(
                "No Smoobu IntegrationConfig yet — running full seed with apartment map."
            )
            from django.core.management import call_command

            call_command(
                "seed_uzorita_smoobu_config",
                tenant_slug=options["tenant_slug"],
                property_slug=options["property_slug"],
                api_key=api_key,
                skip_verify=options["skip_verify"],
            )
            return

        config = row.get_config_dict()
        config["api_key"] = api_key
        if not config.get("apartments"):
            config["apartments"] = apartments_config_payload()
        row.set_config_dict(config)
        row.save(update_fields=["config_encrypted", "config", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(f"Rotated Smoobu api_key on IntegrationConfig id={row.pk}.")
        )
