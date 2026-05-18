from django.core.management.base import BaseCommand
from django.db import transaction

from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant, TenantDomain


class Command(BaseCommand):
    help = "Create demo tenant with domain, property, and sample units."

    @transaction.atomic
    def handle(self, *args, **options):
        tenant, created = Tenant.objects.get_or_create(
            slug="demo",
            defaults={
                "name": "Demo Stay",
                "status": Tenant.Status.ACTIVE,
                "timezone": "Europe/Zagreb",
                "default_language": "hr",
            },
        )
        if not created:
            self.stdout.write(self.style.WARNING("Tenant 'demo' already exists — updating metadata."))
            tenant.name = "Demo Stay"
            tenant.timezone = "Europe/Zagreb"
            tenant.default_language = "hr"
            tenant.status = Tenant.Status.ACTIVE
            tenant.save()

        TenantDomain.objects.update_or_create(
            domain="demo.stay.hr",
            defaults={
                "tenant": tenant,
                "domain_type": TenantDomain.DomainType.STAY_SUBDOMAIN,
                "is_primary": True,
                "is_verified": False,
            },
        )

        prop, _ = Property.objects.get_or_create(
            tenant=tenant,
            slug="demo",
            defaults={
                "name": "Demo Property",
                "address": "Demo ulica 1, Zagreb",
                "contact": {"email": "demo@stay.hr", "phone": "+3851000000"},
                "branding": {
                    "primary_color": "#1a5f7a",
                    "logo_url": "",
                },
            },
        )

        units = [
            ("STD-01", "Standard Double", 2, 0),
            ("STD-02", "Standard Twin", 2, 1),
            ("APT-01", "Apartment", 4, 2),
        ]
        for code, name, adults, children in units:
            Unit.objects.update_or_create(
                tenant=tenant,
                property=prop,
                code=code,
                defaults={
                    "name": name,
                    "capacity_adults": adults,
                    "capacity_children": children,
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("Demo tenant ready."))
        self.stdout.write(f"  Tenant slug: {tenant.slug}")
        self.stdout.write("  Domain: demo.stay.hr (is_verified=False until DNS is ready)")
        self.stdout.write(f"  Property: {prop.slug}")
        self.stdout.write(
            "\nNext: python manage.py create_api_app --tenant demo --name \"Demo Flutter\""
        )
