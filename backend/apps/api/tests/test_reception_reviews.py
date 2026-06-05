from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.integrations.channex.booking_service import channex_external_id
from apps.integrations.models import ChannexReview, IntegrationConfig
from apps.properties.models import Property, Unit
from apps.reservations.models import Reservation
from apps.tenants.models import ChannelManager, Tenant, TenantMembership, TenantReceptionSettings

User = get_user_model()


class ReceptionReviewsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="demo", name="Demo")
        TenantReceptionSettings.objects.create(
            tenant=self.tenant,
            channel_manager=ChannelManager.CHANNEX,
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            slug="channex-demo",
            name="Demo",
            timezone="Europe/Zagreb",
        )
        self.unit = Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code="BCOM-STUDIO",
            name="Studio",
        )
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict(
            {
                "property_id": "prop-id",
                "sync_property_slug": "channex-demo",
            }
        )
        self.integration.save()
        self.booking_id = "channex-booking-1"
        self.reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id=channex_external_id(self.booking_id),
            import_source="channex",
            booking_code="5307026805",
            check_in=date(2026, 6, 20),
            check_out=date(2026, 6, 21),
            booker_name="Guest Test",
            status=Reservation.Status.EXPECTED,
        )
        self.review = ChannexReview.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            channex_review_id="review-uuid-1",
            channex_booking_id=self.booking_id,
            ota="BookingCom",
            content="Excellent stay",
            overall_score=Decimal("9.5"),
            is_replied=False,
            received_at=timezone.now(),
            expired_at=timezone.now() + timedelta(days=30),
        )

        self.staff = User.objects.create_user(
            username="evan",
            password="secret-pass",
            is_staff=True,
        )
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant)
        self.client = APIClient()

    def _login(self):
        response = self.client.post(
            "/api/v1/auth/reception-login/",
            {"username": "evan", "password": "secret-pass"},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)

    def test_list_reviews(self):
        self._login()
        response = self.client.get(
            "/api/v1/reception/reviews/?sync=0",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["reviews"]), 1)
        self.assertEqual(data["reviews"][0]["content"], "Excellent stay")
        self.assertEqual(data["reviews"][0]["reservation_ref"], "5307026805")
        self.assertTrue(data["reviews"][0]["reservation_linkable"])

    def test_list_reviews_relinks_unlinked_review(self):
        unlinked = ChannexReview.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=None,
            channex_review_id="review-uuid-unlinked",
            ota="BookingCom",
            ota_reservation_id="5307026805",
            content="Late-linked review",
            overall_score=Decimal("8.0"),
            is_replied=False,
            received_at=timezone.now(),
        )
        self.assertIsNone(unlinked.reservation_id)

        self._login()
        response = self.client.get(
            "/api/v1/reception/reviews/?sync=0",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        unlinked_payload = next(
            item for item in data["reviews"] if item["id"] == unlinked.pk
        )
        self.assertEqual(unlinked_payload["reservation_id"], self.reservation.pk)
        self.assertTrue(unlinked_payload["reservation_linkable"])
        unlinked.refresh_from_db()
        self.assertEqual(unlinked.reservation_id, self.reservation.pk)

    def test_reply_dict_upsert_normalization(self):
        from apps.integrations.channex.review_service import upsert_channex_review_from_payload

        row, created, _ = upsert_channex_review_from_payload(
            tenant=self.tenant,
            integration=self.integration,
            payload={
                "id": "review-uuid-dict-reply",
                "ota": "BookingCom",
                "reply": {"reply": "Hvala na boravku"},
                "is_replied": False,
            },
        )
        self.assertTrue(created)
        self.assertEqual(row.reply, "Hvala na boravku")
        self.assertTrue(row.is_replied)

        self._login()
        response = self.client.get(
            f"/api/v1/reception/reviews/{row.pk}/?sync=0",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reply"], "Hvala na boravku")
        self.assertTrue(data["is_replied"])

    def test_reply_legacy_string_repair(self):
        from apps.integrations.channex.review_service import repair_channex_review_replies

        row = ChannexReview.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=self.reservation,
            channex_review_id="review-uuid-legacy-reply",
            ota="BookingCom",
            reply="{'reply': 'Stari format odgovora'}",
            is_replied=False,
            received_at=timezone.now(),
        )

        repaired = repair_channex_review_replies(self.tenant)
        self.assertEqual(repaired, 1)
        row.refresh_from_db()
        self.assertEqual(row.reply, "Stari format odgovora")
        self.assertTrue(row.is_replied)
        self.assertIsNotNone(row.reply_sent_at)

    def test_review_links_by_ota_reservation_id(self):
        from apps.integrations.channex.review_service import upsert_channex_review_from_payload

        row, created, _ = upsert_channex_review_from_payload(
            tenant=self.tenant,
            integration=self.integration,
            payload={
                "id": "review-uuid-2",
                "ota": "BookingCom",
                "ota_reservation_id": "5307026805",
                "content": "Great stay",
            },
        )
        self.assertTrue(created)
        self.assertEqual(row.reservation_id, self.reservation.pk)
        self.assertEqual(row.ota_reservation_id, "5307026805")

    @patch("apps.integrations.channex.review_service.translate_text")
    def test_review_translation_cached(self, mock_translate):
        mock_translate.return_value = "Odličan boravak"
        self._login()
        url = f"/api/v1/reception/reviews/{self.review.pk}/?lang=hr&translate=1"
        response = self.client.get(url, HTTP_HOST="app.stay.hr")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["content_localized"], "Odličan boravak")
        self.assertTrue(data["content_is_translated"])
        mock_translate.assert_called_once()

        mock_translate.reset_mock()
        response2 = self.client.get(url, HTTP_HOST="app.stay.hr")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.json()["content_localized"], "Odličan boravak")
        mock_translate.assert_not_called()

    @patch("apps.integrations.channex.review_service.complete_chat")
    @patch("apps.integrations.channex.review_service.llm_configured", return_value=True)
    def test_compose_reply(self, _mock_llm, mock_chat):
        mock_chat.return_value = "Thank you for staying with us!"
        self._login()
        response = self.client.post(
            f"/api/v1/reception/reviews/{self.review.pk}/compose-reply/",
            {"hint": "mention breakfast"},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["body_text"], "Thank you for staying with us!")
        self.assertTrue(data["llm_used"])

    def test_reservation_reviews(self):
        self._login()
        response = self.client.get(
            f"/api/v1/reception/reservations/{self.reservation.pk}/reviews/?sync=0",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reservation_id"], self.reservation.pk)
        self.assertEqual(len(data["reviews"]), 1)

    def test_reservation_reviews_relinks_unlinked(self):
        unlinked = ChannexReview.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            reservation=None,
            channex_review_id="review-uuid-res-unlinked",
            ota="BookingCom",
            ota_reservation_id="5307026805",
            content="Reservation endpoint relink",
            overall_score=Decimal("8.0"),
            is_replied=False,
            received_at=timezone.now(),
        )
        self.assertIsNone(unlinked.reservation_id)

        self._login()
        response = self.client.get(
            f"/api/v1/reception/reservations/{self.reservation.pk}/reviews/?sync=0",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        review_ids = [item["id"] for item in data["reviews"]]
        self.assertIn(unlinked.pk, review_ids)
        unlinked.refresh_from_db()
        self.assertEqual(unlinked.reservation_id, self.reservation.pk)

    @patch("apps.integrations.channex.review_service.ChannexClient")
    def test_reply_to_review(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.reply_to_review.return_value = {
            "data": {
                "id": "review-uuid-1",
                "attributes": {
                    "id": "review-uuid-1",
                    "reply": "Thank you!",
                    "is_replied": True,
                    "booking_id": self.booking_id,
                    "ota": "BookingCom",
                },
            }
        }
        mock_client_cls.return_value = mock_client

        self._login()
        response = self.client.post(
            f"/api/v1/reception/reviews/{self.review.pk}/reply/",
            {"reply": "Thank you!"},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_replied"])
        self.assertEqual(data["reply"], "Thank you!")

    @patch("apps.integrations.channex.review_service.ChannexClient")
    def test_reply_to_review_channex_dict_reply(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.reply_to_review.return_value = {
            "data": {
                "id": "review-uuid-1",
                "attributes": {
                    "id": "review-uuid-1",
                    "reply": {"reply": "Hvala vam na ocjeni"},
                    "is_replied": False,
                    "booking_id": self.booking_id,
                    "ota": "BookingCom",
                },
            }
        }
        mock_client_cls.return_value = mock_client

        self._login()
        response = self.client.post(
            f"/api/v1/reception/reviews/{self.review.pk}/reply/",
            {"reply": "Hvala vam na ocjeni"},
            format="json",
            HTTP_HOST="app.stay.hr",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_replied"])
        self.assertEqual(data["reply"], "Hvala vam na ocjeni")
        self.review.refresh_from_db()
        self.assertEqual(self.review.reply, "Hvala vam na ocjeni")
        self.assertTrue(self.review.is_replied)
        self.assertIsNotNone(self.review.reply_sent_at)
