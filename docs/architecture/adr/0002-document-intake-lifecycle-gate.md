# ADR 0002: Document intake lifecycle gate

## Status

Accepted (2026-07) — u tijeku implementacije po fazama (PR-A … PR-F)

## Summary

**Why:** Incident #938 — zombie batch session + stuck job na terminalnoj rezervaciji (`checked_out`, waived, docs complete) — reconcile je svakih 15 min slao outbound remindere (`hint=id missing sides`) jer nije postojao centralni lifecycle gate.

**How:** Read-only gate `guest_document_intake_automation_allowed()` + audit reason kodovi; event-driven GC i reconcile safety net dolaze u PR-B–D. Gate pokriva **samo** WhatsApp document intake automatizaciju, ne cijeli WhatsApp kanal.

**Rollback:** `WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE=false` + `docker compose up -d django celery-worker`.

## Context

- Race 26.6.–30.6.: `PROCESSING` session nije bio u `_ACTIVE_STATUSES` → paralelni sessioni (#17 / #18).
- Fix `b09c135` sprječava nove race-ove, ali ne čisti postojeće zombie entitete.
- Guardovi za `waived` i `docs_complete` bili su raspršeni; terminalni statusi rezervacije (`checked_out`, …) nisu bili pokriveni u `assess_batch_after_quiet` / finalize / reconcile.

## Decision

1. **Jedna read-only odlučna točka** — `backend/apps/integrations/whatsapp/guest_document_lifecycle.py`
2. **Feature flag** — `WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE` (default `true`); kad je `false`, terminalni statusi se ne blokiraju (legacy).
3. **Audit trail** — `automation_blocked reservation_id=… reason=…` (`LifecycleBlockReason`).
4. **Reconcile = safety net** (PR-D), ne primarni lifecycle mehanizam.
5. **Event-driven close + GC** (PR-B/C) — zatvaranje sessiona i supersede jobova na apply/waive/checkout.

## Invarijante (referenca)

Puna lista: [`document-intake-lifecycle-invariants.md`](../document-intake-lifecycle-invariants.md).

| ID | Invarijanta | PR-A | Napomena |
|----|-------------|:----:|----------|
| I1 | Najviše jedan aktivni batch session po rezervaciji | — | PR-B/C |
| I2 | Najviše jedan aktivni intake job po sessionu | — | PR-B/C |
| I3 | `docs_complete` ⇒ nema outbound document intake automatizacije | ✓ | Gate + call siteovi |
| I4 | Terminalni status ⇒ nema document intake automatizacije | ✓ | Kad je flag uključen |
| I5 | `waived` ⇒ nema document intake automatizacije | ✓ | Uvijek (flag on/off) |
| I6 | `applied` job ⇒ stariji WA jobovi terminalni | — | PR-B/C |
| I7 | Reservation closed ⇒ nema active sessiona | — | PR-B/C + PR-F |

## Alternatives considered

| Alternative | Why not chosen |
|-------------|----------------|
| Samo produžiti reconcile cooldown | Ne zaustavlja spam na zombie entitetima |
| Hardcode skip #938 | Isti pattern na drugim rezervacijama |
| Reconcile kao primarni lifecycle | Event-driven mora biti prvi |
| Gate koji blokira cijeli WhatsApp | Blokira legit arrival/eVisitor/post-checkin |

## References

- Plan: guest document batch lifecycle (v4)
- Invarijante: [`document-intake-lifecycle-invariants.md`](../document-intake-lifecycle-invariants.md)
- Kod: `guest_document_lifecycle.py`, `whatsapp_document_batch.py`, `apply_reply.py`, `document_intake_finalize.py`

---

## Implementation log

**Pravilo:** nakon svakog mergeanog PR-a (A–F) dodati redak u tablicu ispod — što je promijenjeno, koje invarijante sada štiti, koji testovi to pokrivaju. PR nije završen dok zapis nije u ADR-u.

| PR | Datum | Promjene | Invarijante | Testovi |
|----|-------|----------|-------------|---------|
| **PR-A** | 2026-07-07 | Novi modul `guest_document_lifecycle.py`: `LifecycleBlockReason`, `guest_document_intake_automation_allowed()`, `check_guest_document_intake_automation()` (audit log). Flag `WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE` u settings + `.env.example`. Refaktor scattered guardova u `whatsapp_document_batch.py` (inbound, reply, `assess_batch_after_quiet`), `apply_reply.py` (`maybe_send_*`), `document_intake_finalize.py` (guest finalize). Arch test: zabrana inline `is_whatsapp_autocheckin_waived` / `is_document_checkin_complete` u caller modulima; gate bez side-effect poziva. | **I3**, **I4** (flag on), **I5** | `apps.integrations.tests.test_guest_document_lifecycle` — gate unit (svi block reasoni, flag on/off, audit log, `block_documents_complete` za post-apply reply); arch (`GuestDocumentLifecycleArchTests`). Regresija: `test_whatsapp_document_batch` (docs complete skip, assess retry → `documents_complete`), `test_whatsapp_autocheckin_waived` (waived media → `waived`), `test_whatsapp_apply_reply`. |
| PR-B/C | — | *pending* | I1, I2, I6, I7 | *pending* |
| PR-D | — | *pending* | I3–I7 (reconcile GC) | *pending* |
| PR-E | — | *pending* | I1–I7 (golden #938) | *pending* |
| PR-F | — | *pending* | I1–I7 (health check) | *pending* |
