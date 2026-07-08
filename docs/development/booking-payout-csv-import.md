# Booking payout CSV import — operativni runbook

Referenca arhitekture: [ADR-0006 — Booking payout financial source](../architecture/adr/0006-booking-payout-financial-source.md).

## Što radi

1. **Upload CSV** (Django admin → Booking payout imports) — parse, match, status `PARSED`.
2. **Apply payout to reservations** (`SyncPolicy.SAFE`) — samo `booking_payout_*` polja; **ne** mijenja `amount` / `commission_amount`.
3. **Primijeni i ispravi** (`SyncPolicy.MANUAL_OVERRIDE`) — per-linija ili bulk; mijenja iznose + payout; payout CSV pobjeđuje PDF.

## CSV format

Booking.com payout export. Obavezni stupci uključuju: `Type`, `Booking number`, `Check-in`, `Checkout`, `Amount`, `Commission`, `Payments Service Fee`, `Net`, `Payout date`, `Payout ID`.

Samo redovi s `Type=Reservation` se uvozе.

## Admin workflow

| Korak | Akcija | Policy |
|-------|--------|--------|
| 1 | Upload CSV na tenant/property | — |
| 2 | Pregled linija, upozorenja | — |
| 3 | „Apply payout to reservations” | `SAFE` |
| 4 | „Primijeni i ispravi” (linija ili bulk) | `MANUAL_OVERRIDE` |

### Reconciliation health

Na change formi importa:

```
Financial reconciliation: 96%
(15 matched · 14 synced · 1 warning · 0 errors)
```

`synced` = linije s `reservation_synced_at` (ručni sync). Različito od `applied_at` (SAFE apply).

### Optimistic locking

Confirm POST šalje `revision`. Ako se import promijenio u međuvremenu: *„Import se promijenio. Osvježite stranicu.”*

## Guardovi

| Guard | Error code | Ponašanje |
|-------|------------|-----------|
| Račun na rezervaciji | `INVOICE_EXISTS` | Blokira MANUAL_OVERRIDE |
| Drugi payout ID | `PAYOUT_ID_CONFLICT` | Blokira sync |
| Nema dozvole | `PERMISSION_DENIED` | Codename `reservations.apply_booking_payout_line` |
| Stale revision | `STALE_REVISION` | Osvježi stranicu |

## Audit (nema Undo)

- `BookingPayoutLine.reservation_before_sync` / `reservation_after_sync` — JSON snapshot
- `Reservation.financial_source` → `booking_payout` nakon uspješnog MANUAL_OVERRIDE
- `reservation_sync_reason` = `booking_payout_override_pdf` kad PDF izvor postoji
- `warnings` se **potpuno regeneriraju** nakon synca

Za vraćanje: ponovni sync s drugim izvorom ili ručna korekcija.

## Import batch statusi

```
PENDING → PARSED → PARTIALLY_SYNCED → APPLIED
                 ↘ APPLIED (sve odjednom)
PENDING → FAILED
```

## Deploy

Nakon promjena modela ili servisa:

```bash
docker compose build django
docker compose exec django python manage.py migrate
docker compose up -d django
```

## Testovi

```bash
./scripts/ensure-test-db.sh
docker compose build django
./scripts/run-tests-postgis.sh apps.reservations.tests.test_booking_payout_sync -v 2
```

## Reception

Frontend `useReservationVersionWatch(payments)` treba reagirati kad sync vrati `SUCCESS` s promjenama (`touch_reservation_version`, scope `payments`).
