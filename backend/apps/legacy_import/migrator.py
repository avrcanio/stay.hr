from __future__ import annotations

import os
from dataclasses import dataclass, field

from django.conf import settings
from django.db import connections, transaction

from apps.integrations.models import IntegrationConfig
from apps.legacy_import.legacy_models import (
    LegacyEvisitorSubmission,
    LegacyGuest,
    LegacyPropertyInfo,
    LegacyReservation,
    LegacyReservationUnit,
    LegacyRoom,
)
from apps.legacy_import.mapping import LEGACY_DB_ALIAS, i18n_pick, map_legacy_status
from apps.properties.models import Property, Unit
from apps.reservations.models import EvisitorSubmission, Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant, TenantDomain


@dataclass
class MigrationStats:
    properties: int = 0
    units: int = 0
    reservations: int = 0
    reservation_units: int = 0
    guests: int = 0
    evisitor_submissions: int = 0
    integration_configs: int = 0
    errors: list[str] = field(default_factory=list)


def legacy_db_configured() -> bool:
    return LEGACY_DB_ALIAS in settings.DATABASES


def assert_legacy_db() -> None:
    if not legacy_db_configured():
        raise RuntimeError(
            "Legacy database not configured. Set UZORITA_DB_* env vars "
            f"to enable the '{LEGACY_DB_ALIAS}' connection."
        )
    connections[LEGACY_DB_ALIAS].ensure_connection()


class UzoritaLegacyMigrator:
    def __init__(
        self,
        *,
        tenant_slug: str = "uzorita",
        property_slug: str = "uzorita",
        dry_run: bool = False,
        skip_evisitor: bool = False,
    ):
        self.tenant_slug = tenant_slug
        self.property_slug = property_slug
        self.dry_run = dry_run
        self.skip_evisitor = skip_evisitor
        self.stats = MigrationStats()
        self._room_code_to_unit: dict[str, Unit] = {}
        self._legacy_reservation_id_to_stay: dict[int, Reservation] = {}
        self._legacy_guest_id_to_stay: dict[int, Guest] = {}

    def run(self) -> MigrationStats:
        assert_legacy_db()
        with transaction.atomic():
            tenant = self._ensure_tenant()
            prop = self._ensure_property(tenant)
            self._migrate_units(tenant, prop)
            self._migrate_reservations(tenant, prop)
            self._migrate_reservation_units(tenant)
            self._migrate_guests(tenant)
            self._migrate_evisitor_submissions(tenant)
            if not self.skip_evisitor:
                self._import_evisitor_config(tenant, prop)
            if self.dry_run:
                transaction.set_rollback(True)
        return self.stats

    def _ensure_tenant(self) -> Tenant:
        tenant, created = Tenant.objects.get_or_create(
            slug=self.tenant_slug,
            defaults={
                "name": "Uzorita",
                "status": Tenant.Status.ACTIVE,
                "timezone": "Europe/Zagreb",
                "default_language": "hr",
            },
        )
        if not created:
            tenant.timezone = "Europe/Zagreb"
            tenant.default_language = "hr"
            tenant.status = Tenant.Status.ACTIVE
            tenant.save(update_fields=["timezone", "default_language", "status", "updated_at"])

        if not self.dry_run:
            TenantDomain.objects.update_or_create(
                domain=f"{self.tenant_slug}.stay.hr",
                defaults={
                    "tenant": tenant,
                    "domain_type": TenantDomain.DomainType.STAY_SUBDOMAIN,
                    "is_primary": True,
                    "is_verified": False,
                },
            )
        return tenant

    def _ensure_property(self, tenant: Tenant) -> Property:
        legacy_prop = (
            LegacyPropertyInfo.objects.using(LEGACY_DB_ALIAS)
            .filter(is_active=True)
            .order_by("id")
            .first()
        )
        name = "Uzorita"
        address = ""
        if legacy_prop:
            name = i18n_pick(legacy_prop.name_i18n) or legacy_prop.code
            address = i18n_pick(legacy_prop.address_i18n)

        prop, created = Property.objects.get_or_create(
            tenant=tenant,
            slug=self.property_slug,
            defaults={"name": name, "address": address, "timezone": "Europe/Zagreb", "language": "hr"},
        )
        if not created and (legacy_prop or address):
            prop.name = name or prop.name
            if address:
                prop.address = address
            prop.timezone = "Europe/Zagreb"
            prop.language = "hr"
            prop.save(update_fields=["name", "address", "timezone", "language", "updated_at"])
        if created:
            self.stats.properties += 1
        return prop

    def _migrate_units(self, tenant: Tenant, prop: Property) -> None:
        for room in LegacyRoom.objects.using(LEGACY_DB_ALIAS).filter(is_active=True).order_by("code"):
            unit, created = Unit.objects.update_or_create(
                tenant=tenant,
                property=prop,
                code=room.code,
                defaults={
                    "name": room.code,
                    "capacity_adults": 2,
                    "capacity_children": 0,
                    "is_active": True,
                },
            )
            self._room_code_to_unit[room.code] = unit
            if created:
                self.stats.units += 1

    def _migrate_reservations(self, tenant: Tenant, prop: Property) -> None:
        for legacy in LegacyReservation.objects.using(LEGACY_DB_ALIAS).order_by("id"):
            booking_code = ""
            if legacy.external_id and legacy.external_id.isdigit():
                booking_code = legacy.external_id

            defaults = {
                "property": prop,
                "legacy_id": legacy.id,
                "booking_code": booking_code,
                "check_in": legacy.check_in_date,
                "check_out": legacy.check_out_date,
                "status": map_legacy_status(legacy.status),
                "booking_status": legacy.booking_status or "",
                "booker_name": legacy.booker_name or "",
                "booker_email": "",
                "booker_phone": legacy.booker_phone or "",
                "booker_country": legacy.booker_country or "",
                "booker_address": legacy.booker_address or "",
                "amount": legacy.total_amount,
                "currency": legacy.currency or "EUR",
                "source": legacy.import_source or "legacy",
                "import_source": legacy.import_source or "",
                "booked_at": legacy.booked_at,
                "units_count": legacy.units_count,
                "persons_count": legacy.persons_count,
                "adults_count": legacy.adults_count,
                "children_count": legacy.children_count,
                "children_ages": legacy.children_ages or "",
                "commission_percent": legacy.commission_percent,
                "commission_amount": legacy.commission_amount,
                "payment_status": legacy.payment_status or "",
                "payment_provider": legacy.payment_provider or "",
                "notes": legacy.notes or "",
                "travel_purpose": legacy.travel_purpose or "",
                "booking_device": legacy.booking_device or "",
                "nights_count": legacy.nights_count,
                "canceled_at": legacy.canceled_at,
                "details_pending": legacy.details_pending,
                "imported_at": legacy.imported_at,
            }
            reservation, created = Reservation.objects.update_or_create(
                tenant=tenant,
                external_id=legacy.external_id,
                defaults=defaults,
            )
            self._legacy_reservation_id_to_stay[legacy.id] = reservation
            if created:
                self.stats.reservations += 1

    def _migrate_reservation_units(self, tenant: Tenant) -> None:
        for legacy in LegacyReservationUnit.objects.using(LEGACY_DB_ALIAS).order_by("id"):
            reservation = self._legacy_reservation_id_to_stay.get(legacy.reservation_id)
            if not reservation:
                self.stats.errors.append(
                    f"ReservationUnit {legacy.id}: missing reservation legacy_id={legacy.reservation_id}"
                )
                continue

            unit = None
            if legacy.room_id:
                room = LegacyRoom.objects.using(LEGACY_DB_ALIAS).filter(pk=legacy.room_id).first()
                if room:
                    unit = self._room_code_to_unit.get(room.code)

            _, created = ReservationUnit.objects.update_or_create(
                tenant=tenant,
                legacy_id=legacy.id,
                defaults={
                    "reservation": reservation,
                    "unit": unit,
                    "sort_order": legacy.sort_order,
                    "room_name": legacy.room_name,
                    "amount": legacy.amount,
                },
            )
            if created:
                self.stats.reservation_units += 1

    def _migrate_guests(self, tenant: Tenant) -> None:
        for legacy in LegacyGuest.objects.using(LEGACY_DB_ALIAS).order_by("id"):
            reservation = self._legacy_reservation_id_to_stay.get(legacy.reservation_id)
            if not reservation:
                self.stats.errors.append(
                    f"Guest {legacy.id}: missing reservation legacy_id={legacy.reservation_id}"
                )
                continue

            guest, created = Guest.objects.update_or_create(
                tenant=tenant,
                legacy_id=legacy.id,
                defaults={
                    "reservation": reservation,
                    "first_name": legacy.first_name,
                    "last_name": legacy.last_name or "",
                    "name": f"{legacy.first_name} {legacy.last_name}".strip(),
                    "email": legacy.email or "",
                    "date_of_birth": legacy.date_of_birth,
                    "document_number": legacy.document_number or "",
                    "nationality": legacy.nationality or "",
                    "sex": legacy.sex or "",
                    "address": legacy.address or "",
                    "date_of_issue": legacy.date_of_issue,
                    "date_of_expiry": legacy.date_of_expiry,
                    "issuing_authority": legacy.issuing_authority or "",
                    "personal_id_number": legacy.personal_id_number or "",
                    "document_additional_number": legacy.document_additional_number or "",
                    "additional_personal_id_number": legacy.additional_personal_id_number or "",
                    "document_code": legacy.document_code or "",
                    "document_type": legacy.document_type or "",
                    "document_country": legacy.document_country or "",
                    "document_country_iso2": legacy.document_country_iso2 or "",
                    "document_country_iso3": legacy.document_country_iso3 or "",
                    "document_country_numeric": legacy.document_country_numeric or "",
                    "mrz_raw_text": legacy.mrz_raw_text or "",
                    "mrz_verified": legacy.mrz_verified,
                    "is_primary": legacy.is_primary,
                    "evisitor_status": legacy.evisitor_status or "",
                    "evisitor_registration_id": legacy.evisitor_registration_id,
                },
            )
            self._legacy_guest_id_to_stay[legacy.id] = guest
            if created:
                self.stats.guests += 1

    def _migrate_evisitor_submissions(self, tenant: Tenant) -> None:
        for legacy in LegacyEvisitorSubmission.objects.using(LEGACY_DB_ALIAS).order_by("id"):
            guest = self._legacy_guest_id_to_stay.get(legacy.guest_id)
            if not guest:
                self.stats.errors.append(
                    f"EvisitorSubmission {legacy.id}: missing guest legacy_id={legacy.guest_id}"
                )
                continue

            _, created = EvisitorSubmission.objects.update_or_create(
                tenant=tenant,
                legacy_id=legacy.id,
                defaults={
                    "guest": guest,
                    "registration_id": legacy.registration_id,
                    "status": legacy.status,
                    "submitted_at": legacy.submitted_at,
                    "error_user_message": legacy.error_user_message or "",
                    "error_system_message": legacy.error_system_message or "",
                    "request_payload": legacy.request_payload or {},
                    "response_payload": legacy.response_payload or {},
                    "created_at": legacy.created_at,
                },
            )
            if created:
                self.stats.evisitor_submissions += 1

    def _import_evisitor_config(self, tenant: Tenant, prop: Property) -> None:
        enabled = os.getenv("UZORITA_EVISITOR_ENABLED", "").lower() in {"1", "true", "yes", "on"}
        username = os.getenv("UZORITA_EVISITOR_USERNAME", "").strip()
        if not enabled and not username:
            return

        facility_code = os.getenv("UZORITA_EVISITOR_FACILITY_CODE", "").strip()
        legacy_prop = LegacyPropertyInfo.objects.using(LEGACY_DB_ALIAS).order_by("id").first()
        if not facility_code and legacy_prop:
            facility_code = (legacy_prop.evisitor_facility_code or "").strip()

        config = {
            "enabled": enabled,
            "env": os.getenv("UZORITA_EVISITOR_ENV", "test").strip().lower(),
            "base_url": os.getenv("UZORITA_EVISITOR_BASE_URL", "").strip(),
            "username": username,
            "password": os.getenv("UZORITA_EVISITOR_PASSWORD", "").strip(),
            "api_key": os.getenv("UZORITA_EVISITOR_API_KEY", "").strip(),
            "facility_code": facility_code,
            "default_arrival_organisation": os.getenv(
                "UZORITA_EVISITOR_DEFAULT_ARRIVAL_ORGANISATION", "I"
            ).strip(),
            "default_offered_service_type": os.getenv(
                "UZORITA_EVISITOR_DEFAULT_OFFERED_SERVICE_TYPE", "noćenje"
            ).strip(),
            "default_payment_category": os.getenv(
                "UZORITA_EVISITOR_DEFAULT_PAYMENT_CATEGORY", "14"
            ).strip(),
            "default_stay_time_from": os.getenv("UZORITA_EVISITOR_DEFAULT_STAY_TIME_FROM", "14:00").strip(),
            "default_stay_time_until": os.getenv(
                "UZORITA_EVISITOR_DEFAULT_STAY_TIME_UNTIL", "10:00"
            ).strip(),
        }

        row, created = IntegrationConfig.objects.update_or_create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.EVISITOR,
            property=prop,
            defaults={"is_active": enabled or bool(username)},
        )
        row.set_config_dict(config)
        row.save(update_fields=["config", "config_encrypted", "is_active", "updated_at"])
        if created:
            self.stats.integration_configs += 1
