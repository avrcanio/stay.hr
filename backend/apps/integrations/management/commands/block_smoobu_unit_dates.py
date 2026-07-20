from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from apps.integrations.smoobu.blocking_service import block_apartment_dates
from apps.integrations.smoobu.exceptions import SmoobuApiError, SmoobuConfigError, SmoobuRatesError
from apps.integrations.smoobu.resolver import get_active_smoobu_integration
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Block Smoobu apartment dates via blocked booking (channel 11). "
        "POST /api/rates available=0 does not close inventory."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=2)
        parser.add_argument("--unit-code", type=str, required=True)
        parser.add_argument("--check-in", type=str, required=True, help="YYYY-MM-DD")
        parser.add_argument("--check-out", type=str, required=True, help="YYYY-MM-DD")
        parser.add_argument("--notice", type=str, default="")
        parser.add_argument("--label", type=str, default="Block")

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant id={tenant_id} not found."))
            return

        try:
            integration = get_active_smoobu_integration(tenant.slug)
            result = block_apartment_dates(
                integration,
                unit_code=options["unit_code"].strip().upper(),
                check_in=date.fromisoformat(options["check_in"]),
                check_out=date.fromisoformat(options["check_out"]),
                notice=options["notice"],
                guest_label=options["label"],
            )
        except (SmoobuConfigError, SmoobuRatesError, SmoobuApiError, ValueError) as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Blocked {result['unit_code']} apartment {result['apartment_id']} "
                f"{result['check_in']} -> {result['check_out']} "
                f"(Smoobu booking {result['smoobu_booking_id']})"
            )
        )
