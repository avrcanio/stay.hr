from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import (
    PUBLIC_BOOKING_SCOPES,
    RECEPTION_DEVICE_SCOPES,
    VALID_SCOPES,
    ApiApplication,
    Tenant,
)

PROFILE_SCOPES = {
    "public": PUBLIC_BOOKING_SCOPES,
    "reception": RECEPTION_DEVICE_SCOPES,
}


class Command(BaseCommand):
    help = "Create an API application and print the raw token once."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug")
        parser.add_argument("--name", required=True, help="Application display name")
        parser.add_argument(
            "--profile",
            choices=sorted(PROFILE_SCOPES),
            default="public",
            help="Scope preset: public (booking widget) or reception (Hospira tablet).",
        )
        parser.add_argument(
            "--scopes",
            default="",
            help="Comma-separated scopes; overrides --profile when set.",
        )

    def handle(self, *args, **options):
        try:
            tenant = Tenant.objects.get(slug=options["tenant"])
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"Tenant '{options['tenant']}' not found.") from exc

        if options["scopes"]:
            scopes = [s.strip() for s in options["scopes"].split(",") if s.strip()]
        else:
            scopes = list(PROFILE_SCOPES[options["profile"]])

        invalid = set(scopes) - VALID_SCOPES
        if invalid:
            raise CommandError(f"Unknown scopes: {', '.join(sorted(invalid))}")

        if set(scopes).intersection({"admin:read", "admin:write"}):
            self.stdout.write(
                self.style.WARNING(
                    "Warning: admin scopes should not be used for Flutter/mobile apps."
                )
            )

        if options["profile"] == "reception" and not options["scopes"]:
            self.stdout.write(
                "Reception device token scopes: "
                + ", ".join(RECEPTION_DEVICE_SCOPES)
            )

        application, raw_token = ApiApplication.create_with_token(
            tenant=tenant,
            name=options["name"],
            scopes=scopes,
        )

        self.stdout.write(self.style.SUCCESS(f"Created API application: {application.name}"))
        self.stdout.write(self.style.WARNING("Copy this token now — it will not be shown again:\n"))
        self.stdout.write(raw_token)
