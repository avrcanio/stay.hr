from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.properties.models import Property, Unit
from apps.tenants.mango_html_seed import (
    DOMAIN,
    PROPERTY_SLUG,
    TENANT_SLUG,
    UNIT_ADULTS,
    UNIT_CODE,
    UNIT_MAX_GUESTS,
    UNIT_NAME,
    DEFAULT_PRIMARY_COLOR,
    default_html_path,
    load_mango_seed_data,
)
from apps.tenants.models import ChannelManager, Tenant, TenantDomain, TenantReceptionSettings


class Command(BaseCommand):
    help = (
        "Create Mango Tourist Apartment tenant (Vodice) with domain, property, "
        "and single apartment unit. Optionally reads metadata from mango.html."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--html-path",
            default=str(default_html_path()),
            help="Path to saved Booking.com HTML (default: repo root mango.html).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        html_path_raw = (options.get("html_path") or "").strip()
        html_path = Path(html_path_raw) if html_path_raw else None
        seed_data = load_mango_seed_data(html_path)

        tenant, created = Tenant.objects.get_or_create(
            slug=TENANT_SLUG,
            defaults={
                "name": seed_data.name,
                "status": Tenant.Status.ACTIVE,
                "timezone": "Europe/Zagreb",
                "default_language": "hr",
            },
        )
        if not created:
            self.stdout.write(
                self.style.WARNING(f"Tenant '{TENANT_SLUG}' already exists — updating metadata.")
            )
            tenant.name = seed_data.name
            tenant.timezone = "Europe/Zagreb"
            tenant.default_language = "hr"
            tenant.status = Tenant.Status.ACTIVE
            tenant.save()

        TenantReceptionSettings.objects.update_or_create(
            tenant=tenant,
            defaults={"channel_manager": ChannelManager.NONE},
        )

        prop, _ = Property.objects.update_or_create(
            tenant=tenant,
            slug=PROPERTY_SLUG,
            defaults={
                "name": seed_data.name,
                "address": seed_data.address,
                "contact": {},
                "branding": {
                    "primary_color": DEFAULT_PRIMARY_COLOR,
                    "logo_url": seed_data.hero_image_url,
                    "site_title": seed_data.name,
                    "description": seed_data.description,
                },
                "language": "hr",
            },
        )

        Unit.objects.update_or_create(
            tenant=tenant,
            property=prop,
            code=UNIT_CODE,
            defaults={
                "name": UNIT_NAME,
                "capacity_max_guests": UNIT_MAX_GUESTS,
                "capacity_adults": UNIT_ADULTS,
                "capacity_children": 0,
                "capacity_infants": 0,
                "is_active": True,
            },
        )

        TenantDomain.objects.update_or_create(
            domain=DOMAIN,
            defaults={
                "tenant": tenant,
                "property": prop,
                "domain_type": TenantDomain.DomainType.STAY_SUBDOMAIN,
                "is_primary": True,
                "is_verified": False,
            },
        )

        html_source = str(html_path) if html_path and html_path.is_file() else "built-in defaults"
        self.stdout.write(self.style.SUCCESS("Mango tenant ready."))
        self.stdout.write(f"  Tenant slug: {tenant.slug}")
        self.stdout.write(f"  Domain: {DOMAIN} (is_verified=False until DNS is ready)")
        self.stdout.write(f"  Property: {prop.slug}")
        self.stdout.write(f"  Unit: {UNIT_CODE} ({UNIT_NAME}, max {UNIT_MAX_GUESTS} guests)")
        self.stdout.write(f"  Metadata source: {html_source}")
        self.stdout.write(
            "\nNext:\n"
            "  1. Admin → Tenant domains → Provision DNS → set is_verified=True\n"
            "  2. Admin → Users → add Tenant access for staff\n"
            f'  3. Optional: python manage.py create_api_app --tenant {TENANT_SLUG} '
            '--name "Mango Hospira" --profile reception'
        )
