from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.evisitor.scope import build_config_scope, format_config_scope_label
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant

_ENABLED_TRUE = frozenset({"true", "1", "yes", "on"})
_ENABLED_FALSE = frozenset({"false", "0", "no", "off"})
_ENABLED_EXPECTED = "true, false, 1, 0, yes, no, on, off"

_REQUIRED_ENV = (
    "DEMO_EVISITOR_USERNAME",
    "DEMO_EVISITOR_PASSWORD",
    "DEMO_EVISITOR_FACILITY_CODE",
    "DEMO_EVISITOR_BASE_URL",
)


def _parse_enabled(raw: str | None, *, default: bool = True) -> bool:
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in _ENABLED_TRUE:
        return True
    if normalized in _ENABLED_FALSE:
        return False
    raise ValueError(
        f'Invalid value for DEMO_EVISITOR_ENABLED: "{raw}". '
        f"Expected one of: {_ENABLED_EXPECTED}."
    )


class Command(BaseCommand):
    help = (
        "Create or update eVisitor IntegrationConfig for a demo tenant from "
        "DEMO_EVISITOR_* environment variables."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="demo")
        parser.add_argument(
            "--property-slug",
            default=None,
            help="Property slug for property-level config (default: demo).",
        )
        parser.add_argument(
            "--tenant-level",
            action="store_true",
            help="Write tenant default config (property=NULL) instead of property-level.",
        )

    def handle(self, *args, **options):
        if options["tenant_level"] and options["property_slug"]:
            raise CommandError("--tenant-level and --property-slug are mutually exclusive.")

        try:
            enabled = _parse_enabled(os.getenv("DEMO_EVISITOR_ENABLED"))
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc

        env = os.getenv("DEMO_EVISITOR_ENV", "test").strip().lower()

        missing = [
            name
            for name in _REQUIRED_ENV
            if not os.getenv(name, "").strip()
        ]
        if env == "test" and not os.getenv("DEMO_EVISITOR_API_KEY", "").strip():
            missing.append("DEMO_EVISITOR_API_KEY")

        if missing:
            self.stderr.write(
                self.style.ERROR(
                    "Missing required environment variables:\n"
                    + "\n".join(f"  {name}" for name in missing)
                )
            )
            raise SystemExit(1)

        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            self.stderr.write(
                self.style.ERROR(f"Tenant not found: {options['tenant_slug']!r}")
            )
            raise SystemExit(1)

        prop_or_none = None
        if not options["tenant_level"]:
            property_slug = options["property_slug"] or "demo"
            prop_or_none = Property.objects.filter(
                tenant=tenant,
                slug=property_slug,
            ).first()
            if prop_or_none is None:
                self.stderr.write(
                    self.style.ERROR(f"Property {property_slug!r} not found")
                )
                raise SystemExit(1)

        config = {
            "enabled": enabled,
            "env": env,
            "base_url": os.getenv("DEMO_EVISITOR_BASE_URL", "").strip(),
            "username": os.getenv("DEMO_EVISITOR_USERNAME", "").strip(),
            "password": os.getenv("DEMO_EVISITOR_PASSWORD", "").strip(),
            "api_key": os.getenv("DEMO_EVISITOR_API_KEY", "").strip(),
            "facility_code": os.getenv("DEMO_EVISITOR_FACILITY_CODE", "").strip(),
            "default_arrival_organisation": os.getenv(
                "DEMO_EVISITOR_DEFAULT_ARRIVAL_ORGANISATION", "I"
            ).strip(),
            "default_offered_service_type": os.getenv(
                "DEMO_EVISITOR_DEFAULT_OFFERED_SERVICE_TYPE", "noćenje"
            ).strip(),
            "default_payment_category": os.getenv(
                "DEMO_EVISITOR_DEFAULT_PAYMENT_CATEGORY", "14"
            ).strip(),
            "default_stay_time_from": os.getenv(
                "DEMO_EVISITOR_DEFAULT_STAY_TIME_FROM", "15:00"
            ).strip(),
            "default_stay_time_until": os.getenv(
                "DEMO_EVISITOR_DEFAULT_STAY_TIME_UNTIL", "11:00"
            ).strip(),
        }

        row, created = IntegrationConfig.objects.update_or_create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.EVISITOR,
            property=prop_or_none,
            defaults={"is_active": True},
        )
        row.set_config_dict(config)
        row.is_active = config["enabled"]
        row.save(
            update_fields=["config_encrypted", "config", "is_active", "updated_at"]
        )

        scope = build_config_scope(row)
        verb = "Created" if created else "Updated"
        self.stdout.write(f"{verb} eVisitor IntegrationConfig id={row.pk}")
        self.stdout.write(f"Created: {'yes' if created else 'no'}")
        self.stdout.write(f"Scope: {format_config_scope_label(scope)}")
        self.stdout.write(f"Environment: {config['env']}")
        self.stdout.write(f"Facility: {config['facility_code']}")
        self.stdout.write(f"Enabled: {'yes' if config['enabled'] else 'no'}")
