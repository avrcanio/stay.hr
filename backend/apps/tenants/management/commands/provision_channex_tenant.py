from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.integrations.models import (
    ChannexAriOutbox,
    ChannexBookingRevision,
    ChannelRatePlan,
    IntegrationConfig,
    RatePlanDay,
    UnitAvailabilityBlock,
    UnitAvailabilityDay,
)
from apps.properties.models import Property, Unit, UnitBathroom, UnitBed
from apps.reservations.models import (
    DocumentScanLog,
    EvisitorSubmission,
    Guest,
    IdRecognitionSample,
    Reservation,
    ReservationUnit,
)
from apps.tenants.models import (
    ChannelManager,
    Tenant,
    TenantDomain,
    TenantMembership,
    TenantReceptionSettings,
)

User = get_user_model()

CHANNEX_TENANT_SLUG = "channex"
DEMO_TENANT_SLUG = "demo"


class Command(BaseCommand):
    help = (
        "Create tenant 'channex', move a Channex certification property to it, "
        "assign staff membership, and remove Channex from demo tenant."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--property-id",
            type=int,
            default=7,
            help="Property pk to move to the channex tenant (default: 7).",
        )
        parser.add_argument(
            "--username",
            default="evan",
            help="Staff username to assign exclusively to channex tenant (default: evan).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned changes without writing to the database.",
        )

    def handle(self, *args, **options):
        property_id = options["property_id"]
        username = (options["username"] or "").strip()
        dry_run = options["dry_run"]

        prop = Property.objects.filter(pk=property_id).select_related("tenant").first()
        if prop is None:
            raise CommandError(f"Property id={property_id} not found.")

        demo_tenant = Tenant.objects.filter(slug=DEMO_TENANT_SLUG).first()
        if demo_tenant is None:
            raise CommandError(f"Tenant '{DEMO_TENANT_SLUG}' not found.")

        user = User.objects.filter(username=username, is_staff=True).first()
        if user is None:
            raise CommandError(f"Staff user '{username}' not found.")

        unit_ids = list(Unit.objects.filter(property_id=property_id).values_list("id", flat=True))
        reservation_ids = list(
            Reservation.objects.filter(property_id=property_id).values_list("id", flat=True)
        )
        guest_ids = list(Guest.objects.filter(reservation_id__in=reservation_ids).values_list("id", flat=True))

        stats = self._count_updates(
            property_id=property_id,
            unit_ids=unit_ids,
            reservation_ids=reservation_ids,
            guest_ids=guest_ids,
            demo_tenant_id=demo_tenant.id,
        )
        self._print_stats(stats, property=prop, username=username, dry_run=dry_run)

        if dry_run:
            return

        with transaction.atomic():
            channex_tenant, tenant_created = Tenant.objects.get_or_create(
                slug=CHANNEX_TENANT_SLUG,
                defaults={
                    "name": "Channex",
                    "status": Tenant.Status.ACTIVE,
                    "timezone": "Europe/Zagreb",
                    "default_language": "hr",
                },
            )
            if not tenant_created:
                channex_tenant.name = "Channex"
                channex_tenant.status = Tenant.Status.ACTIVE
                channex_tenant.timezone = "Europe/Zagreb"
                channex_tenant.default_language = "hr"
                channex_tenant.save(
                    update_fields=["name", "status", "timezone", "default_language", "updated_at"]
                )

            TenantReceptionSettings.objects.update_or_create(
                tenant=channex_tenant,
                defaults={"channel_manager": ChannelManager.CHANNEX},
            )

            TenantDomain.objects.update_or_create(
                domain="channex.stay.hr",
                defaults={
                    "tenant": channex_tenant,
                    "property": prop,
                    "domain_type": TenantDomain.DomainType.STAY_SUBDOMAIN,
                    "is_primary": True,
                    "is_verified": False,
                },
            )

            TenantMembership.objects.get_or_create(user=user, tenant=channex_tenant)
            removed_memberships = TenantMembership.objects.filter(user=user).exclude(
                tenant=channex_tenant
            ).delete()[0]

            new_tenant_id = channex_tenant.id
            self._apply_updates(
                new_tenant_id=new_tenant_id,
                property_id=property_id,
                unit_ids=unit_ids,
                reservation_ids=reservation_ids,
                guest_ids=guest_ids,
                demo_tenant_id=demo_tenant.id,
            )

            demo_settings, _ = TenantReceptionSettings.objects.get_or_create(
                tenant=demo_tenant,
                defaults={"channel_manager": ChannelManager.NONE},
            )
            if demo_settings.channel_manager != ChannelManager.NONE:
                demo_settings.channel_manager = ChannelManager.NONE
                demo_settings.save(update_fields=["channel_manager", "updated_at"])

            deactivated = (
                IntegrationConfig.objects.filter(
                    tenant=demo_tenant,
                    provider=IntegrationConfig.Provider.CHANNEX,
                    is_active=True,
                ).update(is_active=False)
            )

        self.stdout.write(self.style.SUCCESS("Channex tenant provisioned."))
        self.stdout.write(f"  Tenant: {channex_tenant.slug} (id={channex_tenant.id})")
        self.stdout.write(f"  Property: {prop.slug} (id={prop.id})")
        self.stdout.write(f"  Staff: {username} (removed {removed_memberships} other membership(s))")
        if deactivated:
            self.stdout.write(f"  Deactivated demo Channex IntegrationConfig rows: {deactivated}")

    def _count_updates(
        self,
        *,
        property_id: int,
        unit_ids: list[int],
        reservation_ids: list[int],
        guest_ids: list[int],
        demo_tenant_id: int,
    ) -> dict[str, int]:
        return {
            "properties": Property.objects.filter(pk=property_id).count(),
            "units": Unit.objects.filter(property_id=property_id).count(),
            "unit_beds": UnitBed.objects.filter(unit_id__in=unit_ids).count(),
            "unit_bathrooms": UnitBathroom.objects.filter(unit_id__in=unit_ids).count(),
            "integration_configs": IntegrationConfig.objects.filter(property_id=property_id).count(),
            "channel_rate_plans": ChannelRatePlan.objects.filter(property_id=property_id).count(),
            "rate_plan_days": RatePlanDay.objects.filter(rate_plan__property_id=property_id).count(),
            "availability_days": UnitAvailabilityDay.objects.filter(unit_id__in=unit_ids).count(),
            "outbox": ChannexAriOutbox.objects.filter(property_id=property_id).count(),
            "availability_blocks": UnitAvailabilityBlock.objects.filter(unit_id__in=unit_ids).count(),
            "reservations": len(reservation_ids),
            "reservation_units": ReservationUnit.objects.filter(reservation_id__in=reservation_ids).count(),
            "guests": len(guest_ids),
            "channex_revisions": ChannexBookingRevision.objects.filter(
                reservation_id__in=reservation_ids
            ).count(),
            "evisitor_submissions": EvisitorSubmission.objects.filter(guest_id__in=guest_ids).count(),
            "document_scan_logs": DocumentScanLog.objects.filter(guest_id__in=guest_ids).count(),
            "id_recognition_samples": IdRecognitionSample.objects.filter(
                reservation_id__in=reservation_ids
            ).count(),
            "demo_channex_configs": IntegrationConfig.objects.filter(
                tenant_id=demo_tenant_id,
                provider=IntegrationConfig.Provider.CHANNEX,
                is_active=True,
            ).count(),
        }

    def _apply_updates(
        self,
        *,
        new_tenant_id: int,
        property_id: int,
        unit_ids: list[int],
        reservation_ids: list[int],
        guest_ids: list[int],
        demo_tenant_id: int,
    ) -> None:
        Property.objects.filter(pk=property_id).update(tenant_id=new_tenant_id)
        Unit.objects.filter(property_id=property_id).update(tenant_id=new_tenant_id)
        UnitBed.objects.filter(unit_id__in=unit_ids).update(tenant_id=new_tenant_id)
        UnitBathroom.objects.filter(unit_id__in=unit_ids).update(tenant_id=new_tenant_id)
        IntegrationConfig.objects.filter(property_id=property_id).update(tenant_id=new_tenant_id)
        ChannelRatePlan.objects.filter(property_id=property_id).update(tenant_id=new_tenant_id)
        RatePlanDay.objects.filter(rate_plan__property_id=property_id).update(tenant_id=new_tenant_id)
        UnitAvailabilityDay.objects.filter(unit_id__in=unit_ids).update(tenant_id=new_tenant_id)
        ChannexAriOutbox.objects.filter(property_id=property_id).update(tenant_id=new_tenant_id)
        UnitAvailabilityBlock.objects.filter(unit_id__in=unit_ids).update(tenant_id=new_tenant_id)
        Reservation.objects.filter(pk__in=reservation_ids).update(tenant_id=new_tenant_id)
        ReservationUnit.objects.filter(reservation_id__in=reservation_ids).update(tenant_id=new_tenant_id)
        Guest.objects.filter(pk__in=guest_ids).update(tenant_id=new_tenant_id)
        ChannexBookingRevision.objects.filter(reservation_id__in=reservation_ids).update(
            tenant_id=new_tenant_id
        )
        EvisitorSubmission.objects.filter(guest_id__in=guest_ids).update(tenant_id=new_tenant_id)
        DocumentScanLog.objects.filter(reservation_id__in=reservation_ids).update(tenant_id=new_tenant_id)
        IdRecognitionSample.objects.filter(reservation_id__in=reservation_ids).update(tenant_id=new_tenant_id)

    def _print_stats(
        self,
        stats: dict[str, int],
        *,
        property: Property,
        username: str,
        dry_run: bool,
    ) -> None:
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.MIGRATE_HEADING(f"{prefix}Provision channex tenant"))
        self.stdout.write(f"  Property: {property.slug} (id={property.id}, tenant={property.tenant.slug})")
        self.stdout.write(f"  Staff: {username}")
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}")
