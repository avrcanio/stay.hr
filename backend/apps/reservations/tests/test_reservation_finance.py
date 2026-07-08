from decimal import Decimal

from django.test import SimpleTestCase

from apps.reservations.reservation_finance import compute_owner_net, format_money_amount


class ComputeOwnerNetTests(SimpleTestCase):
    def test_decimal_precision(self):
        self.assertEqual(
            compute_owner_net(Decimal("92.65"), Decimal("16.68")),
            Decimal("75.97"),
        )

    def test_none_amount(self):
        self.assertIsNone(compute_owner_net(None, Decimal("10")))

    def test_none_commission(self):
        self.assertIsNone(compute_owner_net(Decimal("100"), None))

    def test_both_none(self):
        self.assertIsNone(compute_owner_net(None, None))

    def test_negative_result(self):
        self.assertEqual(
            compute_owner_net(Decimal("10"), Decimal("15")),
            Decimal("-5"),
        )


class FormatMoneyAmountTests(SimpleTestCase):
    def test_two_decimal_places(self):
        self.assertEqual(format_money_amount(Decimal("75.9")), "75.90")

    def test_trailing_zeros_preserved(self):
        self.assertEqual(format_money_amount(Decimal("75.00")), "75.00")

    def test_rounds_to_two_decimals(self):
        self.assertEqual(format_money_amount(Decimal("75.999")), "76.00")
