from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.integrations.channex.review_service import (
    REVIEWS_SYNC_CACHE_PREFIX,
    list_reviews_for_property,
    mark_reviews_synced,
    reservation_should_auto_sync_reviews,
    reviews_sync_is_stale,
)
from apps.integrations.models import ChannexReview, IntegrationConfig
from apps.properties.models import Property
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class ChannexReviewSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(slug="uzorita", name="Uzorita")
        self.property = Property.objects.create(tenant=self.tenant, name="Uzorita", slug="uzorita")
        self.integration = IntegrationConfig.objects.create(
            tenant=self.tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
        )
        self.integration.set_config_dict({"property_id": "prop-id"})
        self.integration.save()
        ChannexReview.objects.create(
            tenant=self.tenant,
            integration=self.integration,
            channex_review_id="existing-review",
            ota="BookingCom",
            overall_score=Decimal("8.0"),
            received_at=timezone.now(),
        )

    def test_reviews_sync_is_stale_without_cache(self):
        self.assertTrue(reviews_sync_is_stale(self.tenant.pk))

    def test_mark_reviews_synced_makes_cache_fresh(self):
        mark_reviews_synced(self.tenant.pk)
        self.assertFalse(reviews_sync_is_stale(self.tenant.pk))

    @patch("apps.integrations.channex.review_service.sync_reviews_from_channex")
    def test_list_reviews_sync_if_stale_pulls_when_cache_missing(self, mock_sync):
        list_reviews_for_property(
            self.integration,
            sync_if_empty=False,
            sync_if_stale=True,
        )
        mock_sync.assert_called_once()

    @patch("apps.integrations.channex.review_service.sync_reviews_from_channex")
    def test_list_reviews_sync_if_stale_skips_when_fresh(self, mock_sync):
        mark_reviews_synced(self.tenant.pk)
        list_reviews_for_property(
            self.integration,
            sync_if_empty=False,
            sync_if_stale=True,
        )
        mock_sync.assert_not_called()

    def test_reservation_should_auto_sync_recent_checkout(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="5856279283",
            check_in=date(2026, 6, 7),
            check_out=date(2026, 6, 8),
            status=Reservation.Status.CHECKED_OUT,
        )
        self.assertTrue(reservation_should_auto_sync_reviews(reservation))

    def test_reservation_should_not_auto_sync_old_checkout(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            booking_code="old-booking",
            check_in=date(2026, 5, 1),
            check_out=date(2026, 5, 2),
            status=Reservation.Status.CHECKED_OUT,
        )
        self.assertFalse(reservation_should_auto_sync_reviews(reservation))

    def tearDown(self):
        cache.delete(f"{REVIEWS_SYNC_CACHE_PREFIX}:{self.tenant.pk}")
