# Property financial report — v1 API contract

Line-item settlement report for property owners: each **checked-out** reservation in a calendar period with gross, commission, net, nights, room labels, and guests.

**Contract stability:** v1 JSON shape is frozen — see [ADR 0003 — Frozen v1 contract](../architecture/adr/0003-property-financial-report.md#frozen-v1-contract). Do not mix this report with reception **monthly statistics** (different date axis and status set); see [ADR 0003 — Difference from statistics.py](../architecture/adr/0003-property-financial-report.md#difference-from-statisticspy-intentional).

## Endpoint

```
GET /api/v1/reception/reports/property-financial/
```

| | |
|--|--|
| **Auth** | Bearer token with `reception:read` scope |
| **Response** | `200` — JSON (default), PDF, or Excel depending on `format` |
| **Content-Type** | `application/json` (default), `application/pdf`, or `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

## Query parameters

| Parameter | Required | Format | Semantics |
|-----------|:--------:|--------|-----------|
| `property_slug` | Multi-property tenants: yes; single-property: optional | string | Resolved via `resolve_property_for_tenant()` |
| `check_out_from` | yes | `YYYY-MM-DD` | Inclusive lower bound: `check_out >= check_out_from` |
| `check_out_to` | yes | `YYYY-MM-DD` | **Inclusive** upper bound for callers (internal query uses half-open `[from, to + 1 day)`) |
| `format` | no | `json` (default), `pdf`, `xlsx` | Export format; invalid value → `400 format_invalid` |

**Example (March 2026):** `check_out_from=2026-03-01&check_out_to=2026-03-31`

**PDF download:** append `&format=pdf` — response is `Content-Disposition: attachment` with filename `property-financial-{slug}-{from}_{to}.pdf`.

**Excel download:** append `&format=xlsx` — same pattern with `.xlsx` extension.

Maximum span: `PROPERTY_FINANCIAL_REPORT_MAX_DAYS` (default **90**). Meta echoes `max_period_days` for UI hints.

## Error responses (400)

All errors return JSON `{ "code": "<code>", ... }`.

| Code | When | Extra fields |
|------|------|--------------|
| `period_invalid` | Missing or unparseable dates; or `check_out_to` before `check_out_from` | — |
| `period_too_long` | `(check_out_to − check_out_from + 1)` exceeds max days | `max_days` (int) |
| `property_required` | Property slug missing/invalid on multi-property tenant | `detail` (string) |
| `format_invalid` | `format` is not `json`, `pdf`, or `xlsx` | — |

## v1 JSON schema

Top-level keys: `meta`, `rows`, `totals`.

Decimal amounts in JSON are **strings** with two fractional digits (e.g. `"150.00"`), matching `_decimal_str()` from reception statistics helpers.

### `meta`

| Field | Type | Semantics |
|-------|------|-----------|
| `property_name` | string | Display name of the resolved property |
| `property_slug` | string | Property slug used for filtering |
| `check_out_from` | string (date) | Echo of request; inclusive lower bound |
| `check_out_to` | string (date) | Echo of request; **inclusive** upper bound |
| `generated_at` | string (ISO 8601) | Server timestamp when the report was built |
| `currency` | string | Report currency (last row currency seen, default EUR) |
| `max_period_days` | integer | Configured max span (`PROPERTY_FINANCIAL_REPORT_MAX_DAYS`) |
| `rows_with_missing_commission` | integer | Count of rows where `commission` is null (net unknown) |

### `rows[]`

One object per reservation with `status = checked_out` and `check_out` in the period.

| Field | Type | Semantics |
|-------|------|-----------|
| `reservation_id` | integer | Primary key |
| `booking_code` | string | Internal booking code (may be empty) |
| `external_id` | string | Channel/external reference (may be empty) |
| `check_in` | string (date) | Arrival date |
| `check_out` | string (date) | Departure date |
| `status` | string | Always `"checked_out"` in v1 |
| `room_labels` | string[] | Room names/codes from `ReservationUnit` |
| `nights` | integer | `_effective_nights()` — prefers `nights_count`, else calendar days |
| `gross` | string | `Reservation.amount`; **`null` amount serializes as `"0.00"`** |
| `commission` | string \| null | `Reservation.commission_amount`; `null` when import omitted commission |
| `net` | string \| null | `gross − commission` when commission known; **`null` when commission is null** |
| `currency` | string | Row currency |
| `source` | string | Booking source/channel (may be empty) |
| `guests` | object[] | See `guests[]` below |

### `rows[].guests[]`

| Field | Type | Semantics |
|-------|------|-----------|
| `name` | string | Guest display name |
| `nationality_iso2` | string | ISO 3166-1 alpha-2 (may be empty) |
| `is_primary` | boolean | Primary guest flag |

### `totals`

Aggregates over all rows in the period.

| Field | Type | Semantics |
|-------|------|-----------|
| `reservation_count` | integer | Number of rows |
| `nights` | integer | Sum of row `nights` |
| `gross` | string | Sum of row gross (`null` amount treated as 0) |
| `commission` | string | Sum of row commission (`null` treated as 0 in sum) |
| `net` | string | Sum of row net **only for rows where net is known** |

When some rows lack commission, `totals.net` excludes those rows; use `meta.rows_with_missing_commission` to flag incomplete settlement data.

## Canonical example

The CI snapshot fixture is the authoritative v1 example:

[`backend/apps/api/tests/fixtures/property_financial_report_snapshot.json`](../../backend/apps/api/tests/fixtures/property_financial_report_snapshot.json)

```json
{
  "meta": {
    "property_name": "Uzorita Luxury Rooms",
    "property_slug": "uzorita",
    "check_out_from": "2026-03-01",
    "check_out_to": "2026-03-31",
    "generated_at": "2026-04-01T08:30:00+02:00",
    "currency": "EUR",
    "max_period_days": 90,
    "rows_with_missing_commission": 1
  },
  "rows": [
    {
      "reservation_id": 0,
      "booking_code": "BK-COMPLETE",
      "external_id": "ext-complete",
      "check_in": "2026-03-10",
      "check_out": "2026-03-13",
      "status": "checked_out",
      "room_labels": ["Soba 101"],
      "nights": 3,
      "gross": "150.00",
      "commission": "15.00",
      "net": "135.00",
      "currency": "EUR",
      "source": "booking.com",
      "guests": [
        {
          "name": "Ana Anić",
          "nationality_iso2": "HR",
          "is_primary": true
        },
        {
          "name": "Petra Petrović",
          "nationality_iso2": "DE",
          "is_primary": false
        }
      ]
    },
    {
      "reservation_id": 0,
      "booking_code": "BK-NO-COMM",
      "external_id": "ext-no-comm",
      "check_in": "2026-03-20",
      "check_out": "2026-03-22",
      "status": "checked_out",
      "room_labels": [],
      "nights": 2,
      "gross": "80.00",
      "commission": null,
      "net": null,
      "currency": "EUR",
      "source": "direct",
      "guests": []
    }
  ],
  "totals": {
    "reservation_count": 2,
    "nights": 5,
    "gross": "230.00",
    "commission": "15.00",
    "net": "135.00"
  }
}
```

(`reservation_id` values are assigned at test runtime; the fixture uses `0` as placeholder.)

## Contract stability

- **Frozen rules:** [ADR 0003 — Frozen v1 contract](../architecture/adr/0003-property-financial-report.md#frozen-v1-contract)
- **CI guard:** [`test_reception_property_financial_report_snapshot.py`](../../backend/apps/api/tests/test_reception_property_financial_report_snapshot.py) asserts live API output matches the fixture (with dynamic `reservation_id`s).
- **Python mirror:** `PropertyFinancialReportResult` in [`types.py`](../../backend/apps/reservations/reports/types.py); JSON mapping in [`reception_report_serializers.py`](../../backend/apps/api/reception_report_serializers.py).

## Difference from monthly statistics

Reception monthly statistics (`GET /api/v1/reception/statistics/monthly/`) bucket revenue by **check-in month** and include `checked_in`, `checked_out`, and `no_show`. This report filters by **check-out date** and includes **only `checked_out`**. Totals for the same calendar month will generally differ — by design. See [ADR 0003](../architecture/adr/0003-property-financial-report.md) and [monthly-statistics-override.md](monthly-statistics-override.md).

## Kod

| Što | Putanja |
|-----|---------|
| Params / result types | `backend/apps/reservations/reports/types.py` |
| Report builder (sole ORM access) | `backend/apps/reservations/reports/property_financial_report.py` |
| PDF / Excel exporters | `backend/apps/reservations/reports/exports/` |
| JSON adapter | `backend/apps/api/reception_report_serializers.py` |
| API view | `backend/apps/api/reception_report_views.py` |
| Snapshot fixture | `backend/apps/api/tests/fixtures/property_financial_report_snapshot.json` |
