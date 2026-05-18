from __future__ import annotations

import random
from dataclasses import dataclass, field

from django.db.models import Count

from apps.integrations.models import IntegrationConfig
from apps.legacy_import.legacy_models import LegacyGuest, LegacyReservation
from apps.legacy_import.mapping import (
    INVALID_OPERATIONAL_AFTER_MIGRATE,
    LEGACY_DB_ALIAS,
    map_legacy_status,
    reservation_fingerprint,
)
from apps.legacy_import.migrator import assert_legacy_db, legacy_db_configured
from apps.reservations.models import Guest, Reservation
from apps.tenants.models import Tenant


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    checks: list[ValidationCheck] = field(default_factory=list)
    manual_sample_external_ids: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(ValidationCheck(name=name, passed=passed, detail=detail))


class UzoritaMigrationValidator:
    def __init__(
        self,
        *,
        tenant_slug: str = "uzorita",
        hash_sample_size: int = 20,
        manual_sample_size: int = 10,
        seed: int = 42,
    ):
        self.tenant_slug = tenant_slug
        self.hash_sample_size = hash_sample_size
        self.manual_sample_size = manual_sample_size
        self.seed = seed
        self.report = ValidationReport()

    def run(self) -> ValidationReport:
        try:
            tenant = Tenant.objects.get(slug=self.tenant_slug)
        except Tenant.DoesNotExist:
            self.report.add("tenant_exists", False, f"Tenant '{self.tenant_slug}' not found.")
            return self.report

        self._check_reservation_counts(tenant)
        self._check_guest_counts(tenant)
        if legacy_db_configured():
            assert_legacy_db()
            self._check_hash_sample(tenant)
        else:
            self.report.add(
                "hash_sample",
                False,
                "Legacy DB not configured; cannot compare fingerprints with Uzorita.",
            )

        self._check_status_distribution(tenant)
        self._check_evisitor_config(tenant)
        self._build_manual_sample(tenant)
        return self.report

    def _check_reservation_counts(self, tenant: Tenant) -> None:
        stay_count = Reservation.objects.filter(tenant=tenant).exclude(external_id="").count()
        if not legacy_db_configured():
            self.report.add(
                "reservation_count",
                stay_count > 0,
                f"Stay reservations={stay_count} (legacy DB unavailable for comparison).",
            )
            return

        legacy_count = LegacyReservation.objects.using(LEGACY_DB_ALIAS).count()
        passed = stay_count == legacy_count
        self.report.add(
            "reservation_count",
            passed,
            f"Uzorita={legacy_count}, Stay={stay_count}",
        )

    def _check_guest_counts(self, tenant: Tenant) -> None:
        stay_count = Guest.objects.filter(tenant=tenant).count()
        if not legacy_db_configured():
            self.report.add(
                "guest_count",
                stay_count > 0,
                f"Stay guests={stay_count} (legacy DB unavailable for comparison).",
            )
            return

        legacy_count = LegacyGuest.objects.using(LEGACY_DB_ALIAS).count()
        passed = stay_count == legacy_count
        self.report.add(
            "guest_count",
            passed,
            f"Uzorita={legacy_count}, Stay={stay_count}",
        )

    def _check_hash_sample(self, tenant: Tenant) -> None:
        if self.hash_sample_size <= 0:
            self.report.add("hash_sample", True, "Skipped (hash_sample_size=0).")
            return

        external_ids = list(
            LegacyReservation.objects.using(LEGACY_DB_ALIAS)
            .order_by("external_id")
            .values_list("external_id", flat=True)
        )
        if not external_ids:
            self.report.add("hash_sample", True, "No legacy reservations to sample.")
            return

        rng = random.Random(self.seed)
        sample_size = min(self.hash_sample_size, len(external_ids))
        sample_ids = (
            external_ids if len(external_ids) <= sample_size else rng.sample(external_ids, sample_size)
        )

        mismatches: list[str] = []
        for external_id in sample_ids:
            legacy = LegacyReservation.objects.using(LEGACY_DB_ALIAS).get(external_id=external_id)
            stay = Reservation.objects.filter(tenant=tenant, external_id=external_id).first()
            if not stay:
                mismatches.append(f"{external_id}: missing on Stay")
                continue

            legacy_guest_count = LegacyGuest.objects.using(LEGACY_DB_ALIAS).filter(
                reservation_id=legacy.id
            ).count()
            stay_guest_count = stay.guests.count()
            legacy_fp = reservation_fingerprint(
                legacy.check_in_date,
                map_legacy_status(legacy.status),
                legacy_guest_count,
            )
            stay_fp = reservation_fingerprint(stay.check_in, stay.status, stay_guest_count)
            if legacy_fp != stay_fp:
                mismatches.append(
                    f"{external_id}: legacy={legacy_fp[:12]} stay={stay_fp[:12]} "
                    f"(status legacy={legacy.status} stay={stay.status}, guests {legacy_guest_count}/{stay_guest_count})"
                )

        passed = not mismatches
        detail = f"Sampled {sample_size} external_id values."
        if mismatches:
            detail += " Mismatches: " + "; ".join(mismatches[:5])
            if len(mismatches) > 5:
                detail += f" (+{len(mismatches) - 5} more)"
        self.report.add("hash_sample", passed, detail)

    def _check_status_distribution(self, tenant: Tenant) -> None:
        invalid = (
            Reservation.objects.filter(tenant=tenant, status__in=INVALID_OPERATIONAL_AFTER_MIGRATE)
            .values("status")
            .annotate(n=Count("id"))
        )
        if not invalid:
            self.report.add(
                "status_distribution",
                True,
                "No pending/confirmed/cancelled operational statuses.",
            )
            return

        parts = [f"{row['status']}={row['n']}" for row in invalid]
        self.report.add(
            "status_distribution",
            False,
            "Invalid operational statuses: " + ", ".join(parts),
        )

    def _check_evisitor_config(self, tenant: Tenant) -> None:
        active = IntegrationConfig.objects.filter(
            tenant=tenant,
            provider=IntegrationConfig.Provider.EVISITOR,
            is_active=True,
        ).exists()
        self.report.add(
            "evisitor_config",
            active,
            "Active eVisitor IntegrationConfig found."
            if active
            else "No active eVisitor IntegrationConfig (tenant or property). "
            "Run migrate with UZORITA_EVISITOR_* env or create config in admin.",
        )

    def _build_manual_sample(self, tenant: Tenant) -> None:
        qs = (
            Reservation.objects.filter(tenant=tenant)
            .exclude(external_id="")
            .order_by("check_in", "external_id")
        )
        ids = list(qs.values_list("external_id", flat=True)[: self.manual_sample_size])
        self.report.manual_sample_external_ids = ids
