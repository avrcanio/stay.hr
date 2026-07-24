from django.test import TestCase

from apps.communications.guest_compose_defaults import DEFAULT_TEXTS, MAPS_LINK
from apps.properties.guest_info import (
    build_guest_facts_for_llm,
    format_wifi_block,
    guest_maps_url,
    guest_text,
    merge_parking_into_guest_info,
    merge_wifi_into_guest_info,
    normalize_guest_info,
    parking_facts_from_guest_info,
    render_parking_reply_text,
    wifi_facts_from_guest_info,
)
from apps.properties.admin_forms import PropertyAdminForm
from apps.properties.models import Property
from apps.properties.uzorita_guest_info import UZORITA_GUEST_INFO
from apps.tenants.models import Tenant


class GuestInfoTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="test", name="Test")
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="test-prop",
            name="Test Property",
        )

    def test_normalize_uzorita_seed(self):
        normalized = normalize_guest_info(UZORITA_GUEST_INFO)
        self.assertEqual(normalized["links"]["maps_url"], MAPS_LINK)
        self.assertIn("entrance", normalized["texts"])
        self.assertTrue(normalized["facts"]["ai_notes"])
        self.assertIn("parking", normalized["facts"])
        wifi = normalized["facts"]["wifi"]
        self.assertEqual(wifi["ssid"], "Uzoritarooms")
        self.assertEqual(wifi["password"], "77777777")

    def test_guest_text_fallback_when_empty(self):
        text = guest_text(self.property, "entrance", "en")
        self.assertEqual(text, DEFAULT_TEXTS["entrance"]["en"])

    def test_guest_text_prefers_property_override(self):
        self.property.guest_info = {
            "texts": {
                "entrance": {"en": "Custom entrance instructions."},
            },
        }
        self.property.save(update_fields=["guest_info"])
        text = guest_text(self.property, "entrance", "en")
        self.assertEqual(text, "Custom entrance instructions.")

    def test_guest_text_format_placeholders(self):
        text = guest_text(self.property, "documents", "en", adults=2)
        self.assertIn("2", text)

    def test_build_guest_facts_for_llm(self):
        self.property.guest_info = UZORITA_GUEST_INFO
        self.property.save(update_fields=["guest_info"])
        facts = build_guest_facts_for_llm(self.property, "en")
        self.assertEqual(facts["maps_url"], MAPS_LINK)
        self.assertIn("entrance", facts)
        self.assertIn("parking", facts)
        self.assertIn("summary", facts["parking"])
        self.assertIn("ai_notes", facts)
        self.assertEqual(facts["wifi"]["ssid"], "Uzoritarooms")
        self.assertEqual(facts["wifi"]["password"], "77777777")

    def test_format_wifi_block_hr(self):
        self.property.guest_info = UZORITA_GUEST_INFO
        self.property.save(update_fields=["guest_info"])
        block = format_wifi_block(self.property, "hr")
        self.assertIn("WiFi: Uzoritarooms", block)
        self.assertIn("Lozinka: 77777777", block)

    def test_format_wifi_block_empty_without_ssid(self):
        self.assertEqual(format_wifi_block(self.property, "en"), "")

    def test_wifi_facts_merge_roundtrip(self):
        merged = merge_wifi_into_guest_info({}, ssid="TestNet", password="secret")
        ssid, password = wifi_facts_from_guest_info(merged)
        self.assertEqual(ssid, "TestNet")
        self.assertEqual(password, "secret")

    def test_property_admin_form_wifi_fields(self):
        self.property.guest_info = UZORITA_GUEST_INFO
        self.property.save(update_fields=["guest_info"])
        form = PropertyAdminForm(instance=self.property)
        self.assertEqual(form.fields["wifi_ssid"].initial, "Uzoritarooms")
        self.assertEqual(form.fields["wifi_password"].initial, "77777777")

        form = PropertyAdminForm(
            data={
                "tenant": self.tenant.pk,
                "name": self.property.name,
                "slug": self.property.slug,
                "address": "",
                "contact": "{}",
                "branding": "{}",
                "guest_info": "{}",
                "timezone": "",
                "language": "",
                "check_in_time": "15:00:00",
                "check_out_time": "11:00:00",
                "after_hours_arrival_policy": "contact",
                "guest_arrival_auto_reply_enabled": True,
                "guest_parking_auto_reply_enabled": True,
                "self_service_mode": "off",
                "self_service_config": "{}",
                "guest_checkin_opens_days_before": 7,
                "whatsapp_autocheckin_enabled": False,
                "whatsapp_autocheckin_time": "08:00:00",
                "whatsapp_autocheckin_email_lead_minutes": 30,
                "tourist_tax_zone": "",
                "tourist_tax_category": "",
                "wifi_ssid": "NewSSID",
                "wifi_password": "newpass",
                "parking_has_private": True,
                "parking_zone_label": "Zone C",
                "parking_price_per_day": "3.50",
                "parking_currency": "EUR",
                "parking_price_notes": "",
                "parking_reservation_required": False,
                "parking_ev_charging": False,
                "parking_large_vehicles_allowed": True,
                "parking_custom_hr": "Uz ulicu.",
                "parking_custom_en": "By the street.",
            },
            instance=self.property,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.property.refresh_from_db()
        ssid, password = wifi_facts_from_guest_info(self.property.guest_info)
        self.assertEqual(ssid, "NewSSID")
        self.assertEqual(password, "newpass")
        parking = parking_facts_from_guest_info(self.property.guest_info)
        self.assertEqual(parking.get("zone_label"), "Zone C")
        self.assertEqual(parking.get("price_per_day"), "3.50")

    def test_guest_maps_url_fallback(self):
        self.assertEqual(guest_maps_url(self.property), MAPS_LINK)

    def test_guest_maps_url_from_property(self):
        self.property.guest_info = {"links": {"maps_url": "https://maps.example/test"}}
        self.property.save(update_fields=["guest_info"])
        self.assertEqual(guest_maps_url(self.property), "https://maps.example/test")
