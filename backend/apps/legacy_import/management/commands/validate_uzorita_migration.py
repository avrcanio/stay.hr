import sys

from django.core.management.base import BaseCommand

from apps.legacy_import.validator import UzoritaMigrationValidator


class Command(BaseCommand):
    help = "Validate Uzorita to Stay data migration (counts, hash sample, status, eVisitor)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument(
            "--hash-sample-size",
            type=int,
            default=20,
            help="Number of random external_id rows for fingerprint comparison.",
        )
        parser.add_argument(
            "--manual-sample-size",
            type=int,
            default=10,
            help="Number of reservations to list for manual admin comparison.",
        )
        parser.add_argument("--seed", type=int, default=42, help="RNG seed for hash sample.")

    def handle(self, *args, **options):
        validator = UzoritaMigrationValidator(
            tenant_slug=options["tenant_slug"],
            hash_sample_size=options["hash_sample_size"],
            manual_sample_size=options["manual_sample_size"],
            seed=options["seed"],
        )
        report = validator.run()

        for check in report.checks:
            style = self.style.SUCCESS if check.passed else self.style.ERROR
            mark = "PASS" if check.passed else "FAIL"
            self.stdout.write(style(f"[{mark}] {check.name}: {check.detail}"))

        if report.manual_sample_external_ids:
            self.stdout.write("\nManual sample (compare in admin vs Uzorita legacy):")
            for external_id in report.manual_sample_external_ids:
                self.stdout.write(f"  - {external_id}")

        if report.passed:
            self.stdout.write(self.style.SUCCESS("\nValidation PASS — gate cleared for reception P0."))
            return

        self.stdout.write(self.style.ERROR("\nValidation FAIL — fix issues before reception P0."))
        sys.exit(1)
