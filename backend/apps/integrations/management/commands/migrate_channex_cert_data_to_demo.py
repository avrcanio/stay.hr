from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.integrations.channex.booking_test import CHANNEX_BOOKING_TEST_PROPERTY_SLUG
from apps.integrations.channex.demo_property import (
    CHANNEX_CERT_TENANT_SLUG,
    CHANNEX_DEMO_PROPERTY_SLUG,
)
from apps.integrations.models import (
    ChannexAriOutbox,
    ChannexBookingRevision,
    ChannelRatePlan,
    RatePlanDay,
    UnitAvailabilityDay,
)
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Move Channex cert data (reservations, ARI, outbox) from uzorita/channex-bcom-test "
        f"to tenant {CHANNEX_CERT_TENANT_SLUG}/{CHANNEX_DEMO_PROPERTY_SLUG}."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-tenant",
            default="uzorita",
            help="Source tenant slug (default: uzorita).",
        )
        parser.add_argument(
            "--source-property",
            default=CHANNEX_BOOKING_TEST_PROPERTY_SLUG,
            help="Source property slug (default: channex-bcom-test).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print counts only, do not update database.",
        )

    def handle(self, *args, **options):
        src_tenant = Tenant.objects.filter(slug=options["source_tenant"]).first()
        dst_tenant = Tenant.objects.filter(slug=CHANNEX_CERT_TENANT_SLUG).first()
        if not src_tenant or not dst_tenant:
            raise CommandError("Source or demo tenant not found.")

        src_prop = Property.objects.filter(
            tenant=src_tenant, slug=options["source_property"]
        ).first()
        dst_prop = Property.objects.filter(
            tenant=dst_tenant, slug=CHANNEX_DEMO_PROPERTY_SLUG
        ).first()
        if not src_prop or not dst_prop:
            raise CommandError("Source or demo certification property not found.")

        unit_map = self._unit_map(src_tenant, src_prop, dst_tenant, dst_prop)
        rate_plan_map = self._rate_plan_map(src_tenant, dst_tenant)

        stats = {
            "reservations": 0,
            "reservation_units": 0,
            "guests": 0,
            "channex_revisions": 0,
            "availability_days": 0,
            "rate_plan_days": 0,
            "outbox": 0,
        }

        if options["dry_run"]:
            stats = self._count(src_tenant, src_prop, unit_map, rate_plan_map)
            self._print_stats(stats, dry_run=True)
            return

        with transaction.atomic():
            stats = self._move_all(
                src_tenant,
                src_prop,
                dst_tenant,
                dst_prop,
                unit_map,
                rate_plan_map,
            )

        self._print_stats(stats, dry_run=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"Cert data now on tenant {CHANNEX_CERT_TENANT_SLUG} "
                f"property {CHANNEX_DEMO_PROPERTY_SLUG} (id={dst_prop.id})"
            )
        )

    def _unit_map(
        self,
        src_tenant: Tenant,
        src_prop: Property,
        dst_tenant: Tenant,
        dst_prop: Property,
    ) -> dict[int, int]:
        mapping: dict[int, int] = {}
        dst_by_code = {
            u.code: u.id
            for u in Unit.objects.filter(tenant=dst_tenant, property=dst_prop)
        }
        for unit in Unit.objects.filter(tenant=src_tenant, property=src_prop):
            dst_id = dst_by_code.get(unit.code)
            if dst_id:
                mapping[unit.id] = dst_id
            else:
                self.stdout.write(
                    self.style.WARNING(f"No demo unit for code {unit.code}, skipping unit map")
                )
        return mapping

    def _rate_plan_map(self, src_tenant: Tenant, dst_tenant: Tenant) -> dict[int, int]:
        mapping: dict[int, int] = {}
        dst_by_channex = {
            rp.channex_rate_plan_id: rp.id
            for rp in ChannelRatePlan.objects.filter(tenant=dst_tenant, is_active=True)
        }
        for rp in ChannelRatePlan.objects.filter(tenant=src_tenant, is_active=True):
            dst_id = dst_by_channex.get(rp.channex_rate_plan_id)
            if dst_id:
                mapping[rp.id] = dst_id
        return mapping

    def _channex_reservation_filter(self) -> Q:
        return Q(import_source="channex") | Q(external_id__startswith="channex:")

    def _count(self, src_tenant, src_prop, unit_map, rate_plan_map):
        res_qs = Reservation.objects.filter(tenant=src_tenant, property=src_prop).filter(
            self._channex_reservation_filter()
        )
        res_ids = list(res_qs.values_list("id", flat=True))
        src_unit_ids = list(unit_map.keys())
        src_rp_ids = list(rate_plan_map.keys())
        return {
            "reservations": len(res_ids),
            "reservation_units": ReservationUnit.objects.filter(
                reservation_id__in=res_ids
            ).count(),
            "guests": Guest.objects.filter(reservation_id__in=res_ids).count(),
            "channex_revisions": ChannexBookingRevision.objects.filter(
                reservation_id__in=res_ids
            ).count(),
            "availability_days": UnitAvailabilityDay.objects.filter(
                unit_id__in=src_unit_ids
            ).count(),
            "rate_plan_days": RatePlanDay.objects.filter(rate_plan_id__in=src_rp_ids).count(),
            "outbox": ChannexAriOutbox.objects.filter(
                tenant=src_tenant, property=src_prop
            ).count(),
        }

    def _move_all(
        self,
        src_tenant: Tenant,
        src_prop: Property,
        dst_tenant: Tenant,
        dst_prop: Property,
        unit_map: dict[int, int],
        rate_plan_map: dict[int, int],
    ) -> dict[str, int]:
        stats = {
            "reservations": 0,
            "reservation_units": 0,
            "guests": 0,
            "channex_revisions": 0,
            "availability_days": 0,
            "rate_plan_days": 0,
            "outbox": 0,
        }

        channex_q = self._channex_reservation_filter()
        res_qs = Reservation.objects.filter(
            tenant=src_tenant, property=src_prop
        ).filter(channex_q)
        res_ids = list(res_qs.values_list("id", flat=True))

        stats["reservations"] = res_qs.update(tenant=dst_tenant, property=dst_prop)

        for src_unit_id, dst_unit_id in unit_map.items():
            updated = ReservationUnit.objects.filter(
                reservation_id__in=res_ids, unit_id=src_unit_id
            ).update(tenant=dst_tenant, unit_id=dst_unit_id)
            stats["reservation_units"] += updated

        stats["reservation_units"] += ReservationUnit.objects.filter(
            reservation_id__in=res_ids
        ).update(tenant=dst_tenant)

        stats["guests"] = Guest.objects.filter(reservation_id__in=res_ids).update(
            tenant=dst_tenant
        )

        stats["channex_revisions"] = ChannexBookingRevision.objects.filter(
            reservation_id__in=res_ids
        ).update(tenant=dst_tenant)

        self._clear_dst_ari_conflicts(dst_tenant, unit_map, rate_plan_map)

        for src_unit_id, dst_unit_id in unit_map.items():
            stats["availability_days"] += UnitAvailabilityDay.objects.filter(
                unit_id=src_unit_id
            ).update(tenant=dst_tenant, unit_id=dst_unit_id)

        for src_rp_id, dst_rp_id in rate_plan_map.items():
            stats["rate_plan_days"] += RatePlanDay.objects.filter(
                rate_plan_id=src_rp_id
            ).update(tenant=dst_tenant, rate_plan_id=dst_rp_id)

        stats["outbox"] = ChannexAriOutbox.objects.filter(
            tenant=src_tenant, property=src_prop
        ).update(tenant=dst_tenant, property=dst_prop)

        return stats

    def _clear_dst_ari_conflicts(
        self,
        dst_tenant: Tenant,
        unit_map: dict[int, int],
        rate_plan_map: dict[int, int],
    ) -> None:
        """Remove demo rows that would collide with unique (tenant, unit/plan, date)."""
        src_unit_ids = list(unit_map.keys())
        dst_unit_ids = list(unit_map.values())
        src_rp_ids = list(rate_plan_map.keys())
        dst_rp_ids = list(rate_plan_map.values())

        src_dates = UnitAvailabilityDay.objects.filter(
            unit_id__in=src_unit_ids
        ).values_list("date", flat=True)
        if src_dates:
            UnitAvailabilityDay.objects.filter(
                tenant=dst_tenant, unit_id__in=dst_unit_ids, date__in=src_dates
            ).delete()

        src_rp_dates = RatePlanDay.objects.filter(
            rate_plan_id__in=src_rp_ids
        ).values_list("date", flat=True)
        if src_rp_dates:
            RatePlanDay.objects.filter(
                tenant=dst_tenant,
                rate_plan_id__in=dst_rp_ids,
                date__in=src_rp_dates,
            ).delete()

    def _print_stats(self, stats: dict[str, int], *, dry_run: bool) -> None:
        prefix = "Would move" if dry_run else "Moved"
        for key, count in stats.items():
            self.stdout.write(f"  {prefix} {key}: {count}")
