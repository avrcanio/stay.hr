# ADR 0006: Booking payout CSV as financial source for manual sync

## Status

Accepted (2026-07)

## Summary

**Why:** Booking.com PDF „Commission and charges” and payout CSV can disagree (e.g. PDF 34,35 vs CSV commission 32,04 + service fee 2,31). Staff need a controlled way to align reservation amounts with the payout CSV.

**How:** One sync service (`sync.py`) with `SyncPolicy.SAFE` (payout fields only, legacy bulk Apply) and `SyncPolicy.MANUAL_OVERRIDE` (amounts + payout, admin „Primijeni i ispravi”). Audit via before/after JSON snapshots and `Reservation.financial_source`; no Undo.

## Context

- Bulk payout CSV upload creates `BookingPayoutImport` + lines in `PARSED` status. Matching compares reservation fields to CSV and stores warnings.
- Legacy „Apply payout to reservations” writes payout metadata only (`booking_payout_*`) and does **not** change `amount` / `commission_amount`.
- PDF import may set gross/commission from confirmation PDF; payout CSV is the authoritative source for **what was actually paid out**.

## Decision

1. **Authoritative sources**
   - Payout CSV = authoritative for payout metadata and, on manual sync, for gross/commission aligned to payout.
   - PDF import remains `financial_source=booking_pdf` until a successful manual sync sets `booking_payout`.

2. **Sync policies**
   - `SyncPolicy.SAFE` — payout fields only; bulk „Apply payout”; does not touch amounts.
   - `SyncPolicy.MANUAL_OVERRIDE` — admin per-line or bulk „Primijeni i ispravi”; writes amounts + payout fields; PDF override is intentional.

3. **Guards**
   - Invoice on reservation blocks amount changes (`INVOICE_EXISTS`).
   - Conflicting existing `booking_payout_id` blocks sync (`PAYOUT_ID_CONFLICT`).
   - Optimistic locking on import batch via `revision`.

4. **Audit (no Undo)**
   - `BookingPayoutLine.reservation_before_sync` / `reservation_after_sync` — string-decimal JSON snapshots.
   - `reservation_sync_reason` for override context (not duplicated in warnings).
   - `warnings` = current reconciliation state; full regenerate after sync.
   - Re-sync with another source if correction is needed.

5. **Import batch state machine**
   - `PARSED` → `PARTIALLY_SYNCED` → `APPLIED` driven by `reservation_synced_at` on matched lines.
   - `_transition_import_status` is the only status writer after sync.

6. **Events**
   - In-process `BookingPayoutLineSynced` dataclass event after successful sync with changes (Slack/email later without touching the service).

## Consequences

### Positive

- Single service boundary; admin and legacy Apply share validation and audit.
- Clear separation between bulk payout apply and manual amount correction.
- Reception can watch `ReservationVersion` scope `payments` after sync.

### Negative

- No one-click Undo; operators rely on audit snapshots and re-sync.
- Two completion signals on lines: `applied_at` (SAFE) and `reservation_synced_at` (MANUAL_OVERRIDE).

## Alternatives considered

- **Separate `line_apply.py` / `bulk_apply.py`** — rejected; logic stays in `sync.py`.
- **Merge warnings on sync** — rejected; full regenerate only.
- **Undo stack** — rejected; audit + re-sync is sufficient for v1.
