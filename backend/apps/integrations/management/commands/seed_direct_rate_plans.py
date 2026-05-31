from django.core.management.base import BaseCommand

from apps.integrations.channex.ari_service import copy_direct_rate_plans_from_booking_com
from apps.properties.models import Property
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Create direct rate plans by copying booking_com plans and RatePlanDay rows."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", required=True)
        parser.add_argument("--property-slug", default="")

    def handle(self, *args, **options):
        tenant_slug = options["tenant_slug"]
        tenant = Tenant.objects.filter(slug=tenant_slug).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {tenant_slug}"))
            return

        property_obj = None
        property_slug = (options.get("property_slug") or "").strip()
        if property_slug:
            property_obj = Property.objects.filter(tenant=tenant, slug=property_slug).first()
            if property_obj is None:
                self.stderr.write(self.style.ERROR(f"Property not found: {property_slug}"))
                return

        created = copy_direct_rate_plans_from_booking_com(
            tenant=tenant,
            property=property_obj,
        )
        self.stdout.write(self.style.SUCCESS(f"Direct rate plans created: {created}"))
