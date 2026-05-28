import type { ChannelRateDay, ObpPolicy, ObpTier } from "@/lib/types";

export type ObpTierTemplate = Pick<ObpTier, "adults" | "children">;

function localeTag(locale: string): string {
  return locale === "hr" ? "hr-HR" : locale === "en" ? "en-GB" : `${locale}-${locale.toUpperCase()}`;
}

function formatMoney(value: string | number, locale: string): string {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return String(value);
  return new Intl.NumberFormat(localeTag(locale), {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(num);
}

function formatRateValue(value: number): string {
  return value.toFixed(2);
}

export function computeNormalRateFromPolicy(baseRateInput: string, policy: ObpPolicy): number | null {
  const baseRate = Number(baseRateInput.trim());
  if (!Number.isFinite(baseRate) || baseRate < 0) return null;
  const adultDelta = Number(policy.adult_delta);
  if (!Number.isFinite(adultDelta)) return null;
  const stepsToMax = Math.max(0, policy.max_adults - policy.base_adults);
  return baseRate + stepsToMax * adultDelta;
}

export function formatObpTierLabel(tier: ObpTier, locale: string): string {
  const isHr = locale.startsWith("hr");
  if (tier.children > 0) {
    return isHr
      ? `${tier.adults} odr. + ${tier.children} dijete`
      : `${tier.adults} ad. + ${tier.children} ch.`;
  }
  return isHr
    ? tier.adults === 1
      ? "1 odr."
      : `${tier.adults} odr.`
    : tier.adults === 1
      ? "1 ad."
      : `${tier.adults} ad.`;
}

export function formatObpTierReductionSuffix(
  tier: ObpTier,
  currency: string,
  locale: string,
): string | null {
  if (tier.children > 0 || !tier.reduction_from_normal) return null;
  return `−${formatMoney(tier.reduction_from_normal, locale)} ${currency}`;
}

export function formatObpTierLine(
  tier: ObpTier,
  currency: string,
  locale: string,
  options?: { showReduction?: boolean },
): string {
  const label = formatObpTierLabel(tier, locale);
  const rate = `${formatMoney(tier.rate, locale)} ${currency}`;
  if (options?.showReduction) {
    const reduction = formatObpTierReductionSuffix(tier, currency, locale);
    if (reduction) {
      return `${label}: ${rate} (${reduction})`;
    }
  }
  return `${label}: ${rate}`;
}

export function formatObpTooltip(
  tiers: ObpTier[] | undefined,
  currency: string,
  locale: string,
  baseLabel?: string,
): string {
  if (!tiers?.length) return "";
  const lines = tiers.map((tier) => formatObpTierLine(tier, currency, locale, { showReduction: true }));
  if (baseLabel) {
    return `${baseLabel}\n${lines.join("\n")}`;
  }
  return lines.join("\n");
}

export function formatObpTierList(
  tiers: ObpTier[] | undefined,
  currency: string,
  locale: string,
): string {
  if (!tiers?.length) return "";
  return tiers
    .map((tier) => formatObpTierLine(tier, currency, locale, { showReduction: true }))
    .join(" · ");
}

export function computeObpTiersFromPolicy(baseRateInput: string, policy: ObpPolicy): ObpTier[] {
  const normalRate = computeNormalRateFromPolicy(baseRateInput, policy);
  if (normalRate === null) return [];

  const adultDelta = Number(policy.adult_delta);
  const childFee = Number(policy.child_fee);
  if (!Number.isFinite(adultDelta) || !Number.isFinite(childFee)) return [];

  const tiers: ObpTier[] = [];
  for (let adults = 1; adults <= policy.max_adults; adults += 1) {
    const reductionSteps = Math.max(0, policy.max_adults - adults);
    const tier: ObpTier = {
      adults,
      children: 0,
      rate: formatRateValue(normalRate - reductionSteps * adultDelta),
    };
    if (reductionSteps > 0) {
      tier.reduction_from_normal = formatRateValue(reductionSteps * adultDelta);
    }
    tiers.push(tier);
  }

  const hasChildTier = policy.tiers_at_default_rate.some((row) => row.children > 0);
  if (hasChildTier) {
    tiers.push({
      adults: policy.max_adults,
      children: 1,
      rate: formatRateValue(normalRate + childFee),
    });
  }

  return tiers;
}

export function channexPushRateFromPolicy(baseRateInput: string, policy: ObpPolicy): string | null {
  const baseRate = Number(baseRateInput.trim());
  if (!Number.isFinite(baseRate) || baseRate < 0) return null;
  if (policy.primary_occupancy_adults <= policy.base_adults) return null;
  const extra = policy.primary_occupancy_adults - policy.base_adults;
  const adultDelta = Number(policy.adult_delta);
  if (!Number.isFinite(adultDelta)) return null;
  return formatRateValue(baseRate + extra * adultDelta);
}

export function obpTierKey(tier: ObpTierTemplate): string {
  return `${tier.adults}-${tier.children}`;
}

export function obpExpandedTierTemplates(
  ratesByDate: Record<string, ChannelRateDay[]> | undefined,
  planCode: string,
): ObpTierTemplate[] {
  if (!ratesByDate) return [];
  for (const rows of Object.values(ratesByDate)) {
    const match = rows.find((row) => row.rate_plan_code === planCode);
    if (match?.obp_tiers && match.obp_tiers.length > 1) {
      return match.obp_tiers.slice(1).map(({ adults, children }) => ({ adults, children }));
    }
  }
  return [];
}

export function obpAnchorAdultsFromRates(
  ratesByDate: Record<string, ChannelRateDay[]> | undefined,
  planCode: string,
): number | null {
  if (!ratesByDate) return null;
  for (const rows of Object.values(ratesByDate)) {
    const match = rows.find((row) => row.rate_plan_code === planCode);
    if (match?.obp_anchor_adults) return match.obp_anchor_adults;
  }
  return null;
}

export function obpRateForTier(
  tiers: ObpTier[] | undefined,
  adults: number,
  children: number,
): string | null {
  return tiers?.find((tier) => tier.adults === adults && tier.children === children)?.rate ?? null;
}

export function obpTierFromRates(
  tiers: ObpTier[] | undefined,
  adults: number,
  children: number,
): ObpTier | null {
  return tiers?.find((tier) => tier.adults === adults && tier.children === children) ?? null;
}
