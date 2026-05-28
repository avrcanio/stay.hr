from decimal import Decimal

from django.test import TestCase

from apps.integrations.pricing.obp import (
    channex_push_rate_for_unit,
    compute_list_rate,
    compute_normal_rate,
    compute_obp_tiers,
    get_obp_policy,
)


class ObpPricingTests(TestCase):
    def test_r1_season_tiers(self):
        base = Decimal("112.81")
        tiers = compute_obp_tiers(base, "R1")
        self.assertEqual(len(tiers), 3)
        self.assertEqual(tiers[0].adults, 1)
        self.assertEqual(tiers[0].rate, Decimal("112.81"))
        self.assertEqual(tiers[1].adults, 2)
        self.assertEqual(tiers[1].rate, Decimal("117.81"))
        self.assertEqual(tiers[2].adults, 2)
        self.assertEqual(tiers[2].children, 1)
        self.assertEqual(tiers[2].rate, Decimal("119.81"))

    def test_r3_season_tiers(self):
        base = Decimal("147.00")
        tiers = compute_obp_tiers(base, "R3")
        self.assertEqual([tier.rate for tier in tiers[:3]], [
            Decimal("147.00"),
            Decimal("152.00"),
            Decimal("157.00"),
        ])
        self.assertEqual(tiers[3].adults, 3)
        self.assertEqual(tiers[3].children, 1)
        self.assertEqual(tiers[3].rate, Decimal("159.00"))

    def test_r3_normal_rate_and_channex_push(self):
        base = Decimal("147.00")
        self.assertEqual(compute_normal_rate(base, "R3"), Decimal("157.00"))
        self.assertEqual(channex_push_rate_for_unit("R3", base), Decimal("157.00"))

    def test_r1_normal_rate_and_channex_push(self):
        base = Decimal("112.81")
        self.assertEqual(compute_normal_rate(base, "R1"), Decimal("117.81"))
        self.assertEqual(channex_push_rate_for_unit("R1", base), Decimal("117.81"))

    def test_r6_channex_push_rate(self):
        base = Decimal("147.00")
        self.assertEqual(channex_push_rate_for_unit("R6", base), Decimal("157.00"))

    def test_compute_list_rate_formula(self):
        base = Decimal("112.81")
        self.assertEqual(
            compute_list_rate(base, 2, 1, unit_code="R1"),
            Decimal("119.81"),
        )

    def test_r3_primary_occupancy_policy(self):
        policy = get_obp_policy("R3")
        self.assertEqual(policy.primary_occupancy_adults, 3)
        self.assertEqual(policy.max_adults, 3)

    def test_r6_primary_occupancy_policy(self):
        policy = get_obp_policy("R6")
        self.assertEqual(policy.primary_occupancy_adults, 3)
        self.assertEqual(policy.max_adults, 3)
