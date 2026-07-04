# Triage: `apps.integrations.tests` na PostGIS-u

## Status

✅ **Integration suite stabilized**

**335 / 335 passing (100%)** · 0 failures · 0 errors

This document is retained as a historical record of the stabilization effort completed in **2026-07**.

---

## Current status (final)

| Metrika | Početno | Kraj |
|---------|--------:|-----:|
| Passed | 315 | **335** |
| Failed | 17 | **0** |
| Errors | 3 | **0** |

| PR | Kategorija | Status |
|----|------------|--------|
| A | Fixture | ✅ |
| B | Stale mock | ✅ |
| C | Dual push contract | ✅ |
| D | WhatsApp send path | ✅ |
| E | i18n / operator | ✅ |
| F | Channex ingest / review | ✅ |

Default smoke:

```bash
./scripts/run-tests-postgis.sh   # → apps.integrations.tests
```

**Zadnji run:** 2026-07-04 (nakon **PR-A** … **PR-E**)  
**Okolina:** `stay_platform_test_db`, `config.settings.test_postgis`, `--keepdb`  
**Rezultat:** 335 testova — **335 OK**, **0 failures**, **0 errors** (~23 s)

| Snapshot | Passed | Failed | Errors |
|----------|-------:|-------:|-------:|
| Početni triage | 315 | 17 | 3 |
| Nakon PR-A | 317 | 17 | 1 |
| Nakon PR-B | 318 | 17 | 0 |
| Nakon PR-C | 322 | 13 | 0 |
| Nakon PR-D | 330 | 5 | 0 |
| Nakon PR-F | 332 | 3 | 0 |
| Nakon PR-E | **335** | **0** | **0** |

---

## Projektno pravilo: PostGIS je referenca

| Platforma | `apps.integrations.tests` | Uloga |
|-----------|---------------------------|--------|
| **PostGIS** (`test_postgis`) | **335/335 OK**, 0 errors (2026-07-04) | **Kanonski** smoke za integracijski sloj |
| SQLite (`config.settings.test`) | 16 failures + 37 errors | Brzi unit testovi OK; **ne** koristiti za integration suite |

Integration testovi ovise o PostgreSQL featureima (`pg_advisory_xact_lock`, unique constraints, …). SQLite više nije referentno okruženje za `apps.integrations.tests`.

---

## Burn-down po PR-u (završeno)

| PR | Kategorija | Početno | Nakon mergea | Status |
|----|------------|--------:|-------------:|--------|
| **A** | Fixture (`sort_order`, `wamid`) | 2 | **0** | ✅ 2026-07-04 |
| **B** | Stale mock (`submit_guest_checkin`) | 1 | **0** | ✅ 2026-07-04 |
| **C** | Dual push (`assert_called_once`) | 4 | **0** | ✅ 2026-07-04 |
| **D** | WhatsApp send path | 8 | **0** | ✅ 2026-07-04 |
| **E** | i18n / operator status | 3 | **0** | ✅ 2026-07-04 |
| **F** | Channex ingest / review | 2 | **0** | ✅ 2026-07-04 |
| | **Errors** | **3** | **0** | ✅ |
| | **Failures** | **17** | **0** | ✅ |

---

## Detalji po PR-u

### PR-A ✅ — Test fixture

| Test | Fix |
|------|-----|
| `test_whole_property_availability.test_qualifies_with_two_core_rooms` | `sort_order=0,1` pri create `ReservationUnit` |
| `test_whatsapp_operator.test_finalize_no_match_enters_awaiting_res_pick` | Jedinstveni outbound `wamid` po `send_text_message` pozivu |

### PR-B ✅ — Stale mock

| Test | Fix |
|------|-----|
| `test_operator_job_complete.test_complete_applies_checkin_and_notifies` | Patch `submit_evisitor_for_reservation` (umjesto uklonjenog `submit_guest_checkin` na modulu); mock vraća listu rezultata po gostu |

### PR-C ✅ — Dual push

Poslovni contract: `reservation.created` dolazi iz post_save signala pri kreiranju rezervacije; warning funkcije šalju **jedan** push s vlastitim `event_type`. Testovi više ne koriste `assert_called_once()` na cijelom mocku.

| Test | Stari assert | Stvarno ponašanje | Fix |
|------|--------------|-------------------|-----|
| `test_flag_appends_note_and_notifies` | `assert_called_once()` | `created` + `channex_rooms_mismatch` | assert po `event_type` |
| `test_ingest_warning_empty_channex_rooms` | isto | isto | isto |
| `test_ingest_warning_multi_room_suspect` | isto | isto | isto |
| `test_ingest_flags_overbooking_when_unit_already_occupied` | `assert_called_once()` | 2× `created` + `overbooking` | assert `reservation.overbooking` |

Helper: `_assert_single_reception_push` u `test_booking_room_mismatch.py`.

### PR-D ✅ — WhatsApp send path

**Analiza:** 8 failurea → **3 stvarna uzroka** (test-only).

| Grupa | Testovi | Uzrok | Fix |
|-------|---------|-------|-----|
| **D1** Stale `send_text_message` mock | `test_send_autocheckin_waived_*`, `test_checkin_ready_*`, `test_complete_documents_second_parking_*` | Produkcija koristi `send_guest_message` → v2 | Patch `send_guest_message` na modulu gdje se importa |
| **D2** Operator notify → welcome sequence | `test_notify_guest_whatsapp_*` | Welcome sequence umjesto `_send_reservation_whatsapp_text` | Patch `send_guest_welcome_entrance_and_ask_arrival`; assert `channel` |
| **D3** Arrival routing + stale status | `test_waived_arrival_*`, `test_complete_documents_parking_*`, `test_expected_docs_complete_arrival_*` | `guest_arrival_inbound` prije autocheckin patha | Assert `guest_arrival_handled`; `process_inbound_message` gdje treba |

### PR-E ✅ — Stale expectation (i18n / operator)

| Test | Uzrok | Fix |
|------|-------|-----|
| `test_alt_phone_code_match_before_checkin_auto_reply_off` | `GuestLanguageResolver` može vratiti EN iako je tenant HR | Assert HR **ili** EN arrival-day hint (`dan dolaska` / `arrival day`) |
| `test_incomplete_message_mentions_unreadable_photos` | Tenant `default_language=de` → `Personalausweis`, ne `ID card` | Assert lokalizirani termin (`Personalausweis`) |
| `test_operator_checkin_finalize` | Handler vraća `prompted`; session prelazi u `AWAITING_CONFIRM` | Assert `status=prompted` + `session.status=AWAITING_CONFIRM` |

### PR-F ✅ — Channex

| Test | Uzrok | Fix |
|------|-------|-----|
| `test_cancelled_revision_without_dates_preserves_units` | `on_commit` callback u `TestCase` | `captureOnCommitCallbacks(execute=True)` |
| `test_reservation_should_auto_sync_recent_checkout` | Fiksni datum izvan 7-dnevnog prozora | `check_out = timezone.localdate() - 1 day` |

---

## Kako ponoviti smoke

```bash
./scripts/ensure-test-db.sh
docker compose build django
./scripts/run-tests-postgis.sh
```

Skripta ispisuje **Integration test summary** (passed / failed / errors / duration).

---

## Povezano

- [test-suite.md](test-suite.md) — recommended workflow
- [AGENTS.md](../../AGENTS.md#backend-testing) — PostGIS test infrastruktura
