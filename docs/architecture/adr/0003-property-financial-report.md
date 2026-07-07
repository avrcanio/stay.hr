# ADR 0003: Property financial report — period, status, and revenue semantics

## Status

Accepted (2026-07)

## Summary

**Why:** Property owners and accountants need a **line-item financial report** for a chosen calendar period (e.g. March 2026): each checked-out reservation with gross, commission, net, nights, room labels, and guests. Reception **monthly statistics** (`statistics.py`) answer a different question — dashboard KPIs bucketed by **check-in month** with a broader status set.

**How:** A dedicated report service filters `checked_out` reservations by **`check_out`** on a **half-open** date interval, aggregates amounts in Python, and exposes JSON via `GET /api/v1/reception/reports/property-financial/`. Period length is capped by `PROPERTY_FINANCIAL_REPORT_MAX_DAYS` (default 90).

**Invariant:** Do not reuse or extend `aggregate_monthly_statistics()` for this report — the semantics differ **by design**. Totals between the two features will not match for the same calendar month.

## Context

Recepcija already exposes monthly statistics (`ReceptionMonthlyStatisticsView` → `aggregate_monthly_statistics()`):

- Revenue is assigned to the **check-in month**.
- “Realized” revenue includes `checked_in`, `checked_out`, and `no_show`.
- Separate buckets exist for reserved (expected + in-house + …) and canceled bookings.
- Overrides via `MonthlyStatisticsOverride` can replace aggregated values.

That model suits **year-over-year dashboard charts**, not an **owner settlement report** where:

1. Only stays that **completed checkout** in the period should appear (cash/accrual aligned with departure).
2. In-house guests (`checked_in`) and no-shows must **not** inflate period revenue.
3. Each reservation is a **row** with guest and room detail for PDF/Excel export (v2).
4. Query cost must stay bounded — ad-hoc ranges cannot scan unbounded history.

## Decision

### Period filter — `check_out`, half-open interval

| Parameter | Semantics |
|-----------|-----------|
| `check_out_from` | Inclusive lower bound: `check_out >= check_out_from` |
| `check_out_to` (API) | **Inclusive** upper bound for callers |
| `check_out_to_exclusive` (internal) | `check_out_to + 1 day`; query uses `check_out < check_out_to_exclusive` |

**Half-open rule:** `[from, to_exclusive)` — a reservation with `check_out = 2026-03-31` is included when `check_out_to = 2026-03-31`; a reservation with `check_out = 2026-04-01` is not.

**Example:** March 2026 report → `check_out_from=2026-03-01`, `check_out_to=2026-03-31` → internal `check_out_to_exclusive=2026-04-01`.

A reservation that **checks in** during March but **checks out** in April does **not** appear in the March report.

### Status filter — only `checked_out`

Include **only** `Reservation.Status.CHECKED_OUT`.

| Status | In report | Rationale |
|--------|:---------:|-----------|
| `checked_out` | ✓ | Stay completed; revenue recognized for settlement |
| `checked_in` | ✗ | Guest still in-house |
| `expected` | ✗ | Not yet realized |
| `no_show` | ✗ | No stay; excluded from owner settlement |
| `canceled` | ✗ | No revenue |
| `refused` / `pending` | ✗ | Non-operational for this report |

### Amount fields

| Field | Source | Notes |
|-------|--------|-------|
| Gross (bruto) | `Reservation.amount` | `null` treated as `0` in row display; totals sum non-null or zero per service rules |
| Commission (provizija) | `Reservation.commission_amount` | May be `null` when import omitted it |
| Net (netto) | `amount − commission_amount` | **`null` when `commission_amount` is missing** — do not infer zero commission |
| Nights | `_effective_nights()` from `statistics.py` | Prefer `nights_count`; else `(check_out − check_in).days`; else `0` |
| Currency | `Reservation.currency` | Report meta carries tenant/property currency; mixed-currency rows are out of scope for v1 |

**Net totals:** Sum net only for rows where net is known. Meta includes `rows_with_missing_commission` so consumers can flag incomplete data.

### Property scope

- Filter `Reservation.property` to the resolved property.
- Multi-property tenants **must** pass `property_slug`; resolution uses `resolve_property_for_tenant()` (same pattern as other reception property-scoped endpoints).
- Single-property tenants may omit slug when exactly one property exists.

### Maximum period length

```python
PROPERTY_FINANCIAL_REPORT_MAX_DAYS = env.int("PROPERTY_FINANCIAL_REPORT_MAX_DAYS", default=90)
```

Validation (`PropertyFinancialReportParams.validate()`):

- `check_out_to_exclusive > check_out_from` — otherwise `period_invalid`
- `(check_out_to_exclusive − check_out_from).days ≤ PROPERTY_FINANCIAL_REPORT_MAX_DAYS` — otherwise `period_too_long` (response includes `max_days`)

Default 90 days covers a quarter or three monthly exports without unbounded table scans. Operators may raise the env var; the API returns `max_period_days` in meta for UI hints.

### Module boundary

```
backend/apps/reservations/reports/
├── types.py                      # Params, rows, totals, result dataclasses
└── property_financial_report.py  # build_property_financial_report() — sole ORM access
```

The API serializer maps `PropertyFinancialReportResult` → JSON only (no ORM, no business logic). Future PDF/Excel/email exporters consume the same result type without touching the database.

### Frozen v1 contract

The property financial report v1 response is **frozen**. Consumers (Reception UI, PDF/Excel exporters, external integrations) may rely on field names and semantics below without silent breaking changes.

**Two layers, one contract:**

| Layer | Source | Role |
|-------|--------|------|
| **Python** | `PropertyFinancialReportResult` and related frozen dataclasses in `backend/apps/reservations/reports/types.py` | Internal service and exporter input |
| **JSON** | `GET /api/v1/reception/reports/property-financial/` via `property_financial_report_to_dict()` in `backend/apps/api/reception_report_serializers.py` | HTTP API for clients |

CI locks the JSON shape with a snapshot test: `backend/apps/api/tests/test_reception_property_financial_report_snapshot.py` against `backend/apps/api/tests/fixtures/property_financial_report_snapshot.json`.

**Compatibility rules (v1):**

| Rule | Detail |
|------|--------|
| **Additive only** | New fields in `meta`, `rows[]`, `totals`, or `guests[]` are allowed only together with an updated snapshot fixture and consumer review |
| **No rename** | Existing JSON key names are not renamed |
| **No removal** | Existing fields are not removed without a new ADR (e.g. v2) |
| **No semantic change** | Meaning of existing fields stays fixed (e.g. `gross`, `net`, inclusive `check_out_to`, half-open internal filter) |
| **Breaking change process** | Contract change → new ADR (e.g. v2) + new endpoint version or explicit frontend migration |

Field-level schema, error codes, and a canonical JSON example: [property-financial-report.md](../../development/property-financial-report.md).

**Exporter rule:** PDF/Excel/email modules under `reports/exports/` consume `PropertyFinancialReportResult` only — no ORM queries or re-aggregation of gross/net in export code.

## Difference from `statistics.py` (intentional)

| Aspect | Monthly statistics (`aggregate_monthly_statistics`) | Property financial report |
|--------|-----------------------------------------------------|---------------------------|
| **Date axis** | `check_in` month | `check_out` in `[from, to_exclusive)` |
| **Statuses (revenue)** | `checked_in`, `checked_out`, `no_show` | `checked_out` only |
| **Granularity** | 12 monthly buckets + YoY comparison | Flat reservation rows + period totals |
| **Reserved / canceled** | Separate buckets | Not included |
| **Overrides** | `MonthlyStatisticsOverride` | Not applied |
| **Output** | Dashboard JSON | Settlement-style line items (+ export v2) |
| **Nights helper** | `_effective_nights()` | Same helper (shared definition only) |

**Do not “fix” divergence** by aligning one feature to the other without a new ADR. Product copy should explain: statistics = operational KPI by arrival month; financial report = completed stays by departure date.

## Consequences

### Positive

- Report matches accountant expectation: “everything that checked out in March.”
- Strict status filter avoids inflating owner statements with in-house or no-show amounts.
- Half-open intervals prevent off-by-one errors at month boundaries.
- Max period protects DB and API latency on large tenants.
- Frozen result type enables PDF/Excel/email without duplicating query logic.

### Negative

- March statistics revenue **≠** March financial report totals when check-in and check-out fall in different months.
- Missing `commission_amount` yields incomplete net totals — importers must populate commission for full settlement.
- v1 is JSON only; owners still need export/delivery (planned v2) for email workflows.

## Alternatives considered

| Alternative | Why not chosen |
|-------------|----------------|
| Reuse `aggregate_monthly_statistics()` with a month parameter | Wrong date axis and status set; no line-item detail |
| Filter by `check_in` like statistics | Misaligns with checkout-based settlement |
| Include `checked_in` for “in-period revenue” | Counts guests still on premises; duplicates dashboard semantics |
| Include `no_show` | No stay occurred; statistics use case ≠ owner report |
| Treat missing commission as `0` net | Hides data-quality gaps; risks incorrect payouts |
| Unbounded date range | Risk of timeouts; 90-day default with env override is sufficient for v1 |
| SQL aggregation instead of Python iteration | Statistics already iterate in Python for `_effective_nights`; consistency over micro-optimization for bounded periods |

## References

- **v1 JSON contract (development):** [property-financial-report.md](../../development/property-financial-report.md)
- **Snapshot fixture (CI):** [property_financial_report_snapshot.json](../../../backend/apps/api/tests/fixtures/property_financial_report_snapshot.json)
- **Snapshot test:** [test_reception_property_financial_report_snapshot.py](../../../backend/apps/api/tests/test_reception_property_financial_report_snapshot.py)
- Plan: Property Financial Report v1 (backend jezgra)
- Monthly statistics: `backend/apps/reservations/statistics.py`, `ReceptionMonthlyStatisticsView`
- Property resolution: `backend/apps/properties/resolution.py`
- Settings: `PROPERTY_FINANCIAL_REPORT_MAX_DAYS` in `backend/config/settings/base.py`, `.env.example`
- Implementation (v1): `backend/apps/reservations/reports/`, `backend/apps/api/reception_report_views.py`
