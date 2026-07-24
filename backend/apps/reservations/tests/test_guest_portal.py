from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.properties.models import Property, SelfServiceMode, Unit
from apps.properties.uzorita_guest_info import UZORITA_GUEST_INFO
from apps.reservations.guest_portal_access import (
    build_guest_portal_url,
    ensure_active_portal_access,
    evaluate_portal_access,
    regenerate_portal_access,
    revoke_portal_access,
)
from apps.reservations.guest_portal_context import build_guest_portal_context
from apps.reservations.models import (
    GuestPortalAccessCreatedFrom,
    GuestPortalAccessStatus,
    Reservation,
    ReservationUnit,
)
from apps.tenants.models import Tenant, TenantDomain


class GuestPortalAccessTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Portal Tenant", slug="portal-tenant")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Portal Property",
            slug="portal-property",
            guest_checkin_opens_days_before=7,
            guest_info=UZORITA_GUEST_INFO,
            contact={"phone": "+385998388513", "whatsapp": "+385998388513"},
            after_hours_contact_phone="+385998388513",
        )
        self.check_in = date(2026, 7, 15)
        self.check_out = date(2026, 7, 18)
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="GP-001",
            check_in=self.check_in,
            check_out=self.check_out,
            adults_count=1,
            booker_name="Ana Anić",
            amount=Decimal("100.00"),
            booker_country="HR",
        )

    def test_ensure_active_portal_access_is_idempotent(self):
        first = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        second = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.WHATSAPP,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.created_from, GuestPortalAccessCreatedFrom.SYSTEM)

    def test_regenerate_revokes_previous_active_access(self):
        first = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.EMAIL,
        )
        old, new = regenerate_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.RECEPTION_MANUAL,
        )
        first.refresh_from_db()
        self.assertEqual(old.pk, first.pk)
        self.assertNotEqual(new.pk, first.pk)
        self.assertEqual(first.status, GuestPortalAccessStatus.REVOKED)
        self.assertEqual(new.status, GuestPortalAccessStatus.ACTIVE)

    def test_evaluate_portal_access_not_open_yet(self):
        access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        tz = ZoneInfo("Europe/Zagreb")
        before_open = datetime(2026, 1, 1, 12, 0, tzinfo=tz)
        result = evaluate_portal_access(access, now=before_open)
        self.assertFalse(result.allowed)
        self.assertEqual(result.http_status, 403)
        self.assertEqual(result.gate_status, "not_open_yet")

    def test_evaluate_portal_access_expired(self):
        access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        tz = ZoneInfo("Europe/Zagreb")
        after_expire = datetime(2026, 12, 1, 12, 0, tzinfo=tz)
        result = evaluate_portal_access(access, now=after_expire)
        self.assertFalse(result.allowed)
        self.assertEqual(result.http_status, 410)
        self.assertEqual(result.gate_status, "expired")

    def test_evaluate_portal_access_revoked(self):
        access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        revoke_portal_access(access)
        result = evaluate_portal_access(access)
        self.assertFalse(result.allowed)
        self.assertEqual(result.http_status, 410)
        self.assertEqual(result.gate_status, "revoked")

    @override_settings(STAY_BOOKING_PUBLIC_URL="https://booking.example.test")
    def test_build_guest_portal_url_uses_tenant_domain_when_present(self):
        TenantDomain.objects.create(
            tenant=self.tenant,
            domain="booking.uzorita.test",
            domain_type=TenantDomain.DomainType.CUSTOM_DOMAIN,
            is_verified=True,
            is_primary=True,
        )
        access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        url = build_guest_portal_url(access, self.reservation)
        self.assertEqual(url, f"https://booking.uzorita.test/g/{access.token}")

    def test_context_includes_core_sections_from_uzorita_guest_info(self):
        access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        ctx = build_guest_portal_context(access, language="en")
        self.assertEqual(ctx.language, "en")
        for section in ("welcome", "arrival", "parking", "wifi", "breakfast", "contact"):
            self.assertIn(section, ctx.sections)
            self.assertIn(section, ctx.content)
        self.assertEqual(ctx.content["wifi"]["ssid"], "Uzoritarooms")
        self.assertIn("maps_url", ctx.content["arrival"])
        self.assertIn("whatsapp_url", ctx.content["contact"])
        self.assertFalse(ctx.self_service_active)
        self.assertNotIn("key_guide", ctx.sections)

    def test_context_includes_key_guide_when_self_service_always(self):
        unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R3",
            name="Room 3",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=unit,
            sort_order=0,
        )
        self.property.self_service_mode = SelfServiceMode.ALWAYS
        self.property.save(update_fields=["self_service_mode", "updated_at"])
        access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        ctx = build_guest_portal_context(access, language="en")
        self.assertTrue(ctx.self_service_active)
        self.assertIn("key_guide", ctx.sections)
        guide = ctx.content["key_guide"]
        self.assertEqual(guide["room_code"], "R3")
        self.assertEqual(guide["key_label"], "3")
        self.assertGreaterEqual(len(guide["steps"]), 8)
        self.assertIn("image_url", guide["steps"][0])
        self.assertIn("3", guide["steps"][5]["caption"])
        self.assertNotIn("{key_label}", guide["steps"][5]["caption"])

    def test_key_guide_omitted_when_schedule_misses_check_in_weekday(self):
        self.property.self_service_mode = SelfServiceMode.SCHEDULE
        self.property.self_service_config = {"weekdays": [1]}  # Tuesday
        self.property.save(
            update_fields=["self_service_mode", "self_service_config", "updated_at"]
        )
        # 2026-07-15 is Wednesday
        self.assertEqual(self.reservation.check_in.weekday(), 2)
        access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        ctx = build_guest_portal_context(access, language="en")
        self.assertFalse(ctx.self_service_active)
        self.assertNotIn("key_guide", ctx.sections)


class GuestPortalPublicAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Portal API", slug="portal-api")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="API Portal Property",
            slug="api-portal-property",
            guest_checkin_opens_days_before=0,
            guest_info=UZORITA_GUEST_INFO,
            contact={"phone": "+385998388513"},
            after_hours_contact_phone="+385998388513",
        )
        today = date.today()
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="GP-API-001",
            check_in=today,
            check_out=today + timedelta(days=2),
            adults_count=1,
            booker_name="API Guest",
            amount=Decimal("100.00"),
            booker_country="DE",
        )
        self.access = ensure_active_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        self.token = str(self.access.token)

    def test_get_portal_returns_sections_and_content(self):
        url = reverse("public-guest-portal", kwargs={"token": self.token})
        response = self.client.get(url, {"lang": "en"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["property_name"], self.property.name)
        self.assertEqual(data["language"], "en")
        self.assertIn("welcome", data["sections"])
        self.assertIn("wifi", data["sections"])
        self.assertEqual(data["content"]["wifi"]["ssid"], "Uzoritarooms")
        self.assertFalse(data["self_service_active"])
        self.assertNotIn("key_guide", data["sections"])

    def test_get_portal_key_guide_and_step_image_when_self_service_always(self):
        unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="R2",
            name="Room 2",
        )
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=self.reservation,
            unit=unit,
            sort_order=0,
        )
        self.property.self_service_mode = SelfServiceMode.ALWAYS
        self.property.save(update_fields=["self_service_mode", "updated_at"])

        url = reverse("public-guest-portal", kwargs={"token": self.token})
        response = self.client.get(url, {"lang": "en"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["self_service_active"])
        self.assertIn("key_guide", data["sections"])
        self.assertEqual(data["content"]["key_guide"]["key_label"], "2")

        step_url = reverse(
            "public-guest-portal-key-guide-step",
            kwargs={"token": self.token, "index": 0},
        )
        step_response = self.client.get(step_url)
        self.assertEqual(step_response.status_code, 200)
        self.assertEqual(step_response["Content-Type"], "image/jpeg")
        body = b"".join(step_response.streaming_content)
        self.assertGreater(len(body), 1000)

    def test_get_portal_unknown_token_404(self):
        import uuid

        url = reverse("public-guest-portal", kwargs={"token": uuid.uuid4()})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_get_portal_not_open_yet_403(self):
        self.property.guest_checkin_opens_days_before = 30
        self.property.save(update_fields=["guest_checkin_opens_days_before", "updated_at"])
        self.reservation.check_in = date.today() + timedelta(days=40)
        self.reservation.check_out = date.today() + timedelta(days=42)
        self.reservation.save(update_fields=["check_in", "check_out", "updated_at"])
        _, access = regenerate_portal_access(
            self.reservation,
            created_from=GuestPortalAccessCreatedFrom.SYSTEM,
        )
        url = reverse("public-guest-portal", kwargs={"token": access.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "not_open_yet")

    def test_get_portal_revoked_410(self):
        revoke_portal_access(self.access)
        url = reverse("public-guest-portal", kwargs={"token": self.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["status"], "revoked")

    def test_get_portal_expired_410(self):
        self.access.expires_at = self.access.opens_at - timedelta(days=1)
        self.access.save(update_fields=["expires_at", "updated_at"])
        url = reverse("public-guest-portal", kwargs={"token": self.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["status"], "expired")
