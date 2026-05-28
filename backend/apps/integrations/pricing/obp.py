"""Occupancy-based pricing (OBP) rules for channel rate display and Channex push."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.integrations.channex.mapping import (
    UZORITA_BOOKING_OBP_ADULT_DELTA,
    UZORITA_BOOKING_OBP_PRIMARY_OCCUPANCY,
)
from apps.properties.occupancy import UZORITA_UNIT_OCCUPANCY

OBP_BASE_ADULTS = 1
OBP_ADULT_DELTA = UZORITA_BOOKING_OBP_ADULT_DELTA
OBP_CHILD_FEE = Decimal("2.00")


@dataclass(frozen=True)
class ObpTier:
    adults: int
    children: int
    rate: Decimal


@dataclass(frozen=True)
class ObpPolicy:
    mode: str = "occupancy"
    base_adults: int = OBP_BASE_ADULTS
    adult_delta: Decimal = OBP_ADULT_DELTA
    child_fee: Decimal = OBP_CHILD_FEE
    max_adults: int = 2
    max_children: int = 0
    primary_occupancy_adults: int = 1

    @property
    def anchor_adults(self) -> int:
        return self.max_adults

    @property
    def channex_primary_offset(self) -> Decimal:
        if self.primary_occupancy_adults <= self.base_adults:
            return Decimal("0")
        extra = self.primary_occupancy_adults - self.base_adults
        return self.adult_delta * extra


def get_obp_policy(unit_code: str) -> ObpPolicy:
    occ = UZORITA_UNIT_OCCUPANCY.get(unit_code, {})
    max_adults = int(occ.get("capacity_adults", 2))
    return ObpPolicy(
        max_adults=max_adults,
        max_children=int(occ.get("capacity_children", 0)),
        primary_occupancy_adults=UZORITA_BOOKING_OBP_PRIMARY_OCCUPANCY.get(
            unit_code,
            max_adults,
        ),
    )


def compute_normal_rate(
    base_rate: Decimal,
    unit_code: str = "",
    *,
    policy: ObpPolicy | None = None,
) -> Decimal:
    """Full/normal price at max adult occupancy (Booking 'Normal price' anchor)."""
    policy = policy or get_obp_policy(unit_code)
    steps_to_max = max(0, policy.max_adults - policy.base_adults)
    return base_rate + policy.adult_delta * steps_to_max


def compute_list_rate(
    base_rate: Decimal,
    adults: int,
    children: int = 0,
    *,
    unit_code: str = "",
) -> Decimal:
    policy = get_obp_policy(unit_code)
    normal = compute_normal_rate(base_rate, unit_code=unit_code, policy=policy)
    reduction_steps = max(0, policy.max_adults - adults)
    return (
        normal
        - policy.adult_delta * reduction_steps
        + policy.child_fee * children
    )


def compute_obp_tiers(base_rate: Decimal, unit_code: str) -> list[ObpTier]:
    policy = get_obp_policy(unit_code)
    tiers: list[ObpTier] = []

    for adults in range(1, policy.max_adults + 1):
        tiers.append(
            ObpTier(
                adults=adults,
                children=0,
                rate=compute_list_rate(base_rate, adults, 0, unit_code=unit_code),
            )
        )

    if policy.max_children > 0:
        tiers.append(
            ObpTier(
                adults=policy.max_adults,
                children=1,
                rate=compute_list_rate(
                    base_rate,
                    policy.max_adults,
                    1,
                    unit_code=unit_code,
                ),
            )
        )

    return tiers


def channex_push_rate_for_unit(unit_code: str, stay_rate: Decimal) -> Decimal:
    """Map stay.hr 1-adult base to Channex primary (normal) rate at primary occupancy."""
    policy = get_obp_policy(unit_code)
    return stay_rate + policy.channex_primary_offset


def _reduction_from_normal(
    tier: ObpTier,
    *,
    policy: ObpPolicy,
) -> Decimal | None:
    if tier.children > 0:
        return None
    steps = max(0, policy.max_adults - tier.adults)
    if steps <= 0:
        return None
    return policy.adult_delta * steps


def serialize_obp_tier(
    tier: ObpTier,
    *,
    policy: ObpPolicy | None = None,
) -> dict[str, int | str]:
    payload: dict[str, int | str] = {
        "adults": tier.adults,
        "children": tier.children,
        "rate": format(tier.rate.quantize(Decimal("0.01")), "f"),
    }
    if policy is not None:
        reduction = _reduction_from_normal(tier, policy=policy)
        if reduction is not None:
            payload["reduction_from_normal"] = format(
                reduction.quantize(Decimal("0.01")),
                "f",
            )
    return payload


def serialize_obp_policy(policy: ObpPolicy, base_rate: Decimal, unit_code: str) -> dict:
    normal_rate = compute_normal_rate(base_rate, unit_code=unit_code, policy=policy)
    return {
        "mode": policy.mode,
        "base_adults": policy.base_adults,
        "adult_delta": format(policy.adult_delta.quantize(Decimal("0.01")), "f"),
        "child_fee": format(policy.child_fee.quantize(Decimal("0.01")), "f"),
        "max_adults": policy.max_adults,
        "primary_occupancy_adults": policy.primary_occupancy_adults,
        "anchor_adults": policy.anchor_adults,
        "normal_rate": format(normal_rate.quantize(Decimal("0.01")), "f"),
        "tiers_at_default_rate": [
            serialize_obp_tier(tier, policy=policy)
            for tier in compute_obp_tiers(base_rate, unit_code)
        ],
    }


def serialize_rate_obp_fields(
    base_rate: Decimal,
    unit_code: str,
) -> dict[str, object]:
    policy = get_obp_policy(unit_code)
    normal_rate = compute_normal_rate(base_rate, unit_code=unit_code, policy=policy)
    push_rate = channex_push_rate_for_unit(unit_code, base_rate)
    payload: dict[str, object] = {
        "obp_tiers": [
            serialize_obp_tier(tier, policy=policy)
            for tier in compute_obp_tiers(base_rate, unit_code)
        ],
        "obp_primary_occupancy_adults": policy.primary_occupancy_adults,
        "obp_anchor_adults": policy.anchor_adults,
        "obp_normal_rate": format(normal_rate.quantize(Decimal("0.01")), "f"),
    }
    if push_rate != base_rate:
        payload["channex_push_rate"] = format(push_rate.quantize(Decimal("0.01")), "f")
    return payload
