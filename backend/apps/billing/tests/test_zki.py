from datetime import datetime
from decimal import Decimal

from django.test import SimpleTestCase

from apps.billing.services.zki import calculate_zki, format_amount_for_zki, format_datetime_for_zki


class ZkiTests(SimpleTestCase):
    def test_format_amount_for_zki(self):
        self.assertEqual(format_amount_for_zki(Decimal("150")), "150,00")
        self.assertEqual(format_amount_for_zki(Decimal("1246.5")), "1246,50")

    def test_format_datetime_for_zki(self):
        dt = datetime(2026, 4, 15, 14, 35, 22)
        self.assertEqual(format_datetime_for_zki(dt), "15.04.2026 14:35:22")

    def test_calculate_zki_is_deterministic(self):
        issued_at = datetime(2026, 4, 15, 14, 35, 22)
        first = calculate_zki(
            oib="12345678901",
            issued_at=issued_at,
            invoice_number="1",
            business_premise_code="PP1",
            payment_device_code="1",
            total=Decimal("150.00"),
        )
        second = calculate_zki(
            oib="12345678901",
            issued_at=issued_at,
            invoice_number="1",
            business_premise_code="PP1",
            payment_device_code="1",
            total=Decimal("150.00"),
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 32)
