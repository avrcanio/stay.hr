# Document intake lifecycle — invarijante

Eksplicitna pravila za WhatsApp document intake automatizaciju. Testiraju se u CI (PR-E) i provjeravaju u `document_intake_health_check` (PR-F).

| ID | Invarijanta | Status |
|----|-------------|--------|
| **I1** | Najviše **jedan aktivni batch session** po rezervaciji | PR-B/C |
| **I2** | Najviše **jedan aktivni intake job** po sessionu (1:1 pri kreiranju) | PR-B/C |
| **I3** | `docs_complete` ⇒ nema outbound document intake automatizacije | **PR-A** (gate) |
| **I4** | `checked_out` / `canceled` / `no_show` / `refused` ⇒ nema document intake automatizacije | **PR-A** (gate, flag on) |
| **I5** | `waived` ⇒ nema document intake automatizacije | **PR-A** (gate) |
| **I6** | `applied` job postoji ⇒ svi stariji WA jobovi za tu rezervaciju su terminalni | PR-B/C |
| **I7** | Reservation closed ⇒ nema active sessiona | PR-B/C, PR-F |

## Gate (PR-A)

- Modul: `backend/apps/integrations/whatsapp/guest_document_lifecycle.py`
- Read-only: nema DB write, nema slanja poruka
- Reason kodovi: `LifecycleBlockReason` (`waived`, `documents_complete`, `checked_out`, …)
- Audit: `automation_blocked reservation_id=… reason=…`
- Flag: `WHATSAPP_DOCUMENT_INTAKE_LIFECYCLE_GATE` — kad je `false`, I4 se ne provjerava (legacy)

## Reference

- ADR: [`adr/0002-document-intake-lifecycle-gate.md`](adr/0002-document-intake-lifecycle-gate.md)
- AGENTS.md — document intake tenant invariant (odvojeno od lifecycle gatea)
