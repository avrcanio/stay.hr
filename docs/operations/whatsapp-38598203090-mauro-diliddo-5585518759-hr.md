# Incident: guest document batch — Mauro Di Liddo (#799)

**Datum:** 2026-06-22  
**Status:** zatvoreno (confirm-flow fix u kodu + ručna korekcija gostiju u bazi)

---

## Metapodaci

| Stavka | Vrijednost |
|--------|------------|
| Gost (booker) | Mauro Di Liddo |
| Telefon | `+385 98 203 090` (`wa_id=38598203090`) |
| Rezervacija | `#799`, booking `5585518759` |
| Objekt | Uzorita B&B |
| Check-in | 2026-06-22 → 2026-06-23, **2 odrasla** |
| Gosti | `Guest` #2186 (primary), #2187 |
| Job | `DocumentIntakeJob` #81 |
| Sesija | `WhatsAppDocumentBatchSession` #13 |

### WhatsApp poruke (UTC)

| ID | Vrijeme | Smjer | Tip | Sadržaj |
|----|---------|-------|-----|---------|
| 540 | 09:11 | outbound | template | Welcome / booking info |
| 541 | 12:18:34 | inbound | button | Auto check in |
| 542 | 12:18:35 | outbound | text | Molimo pošaljite dokumente |
| 543 | 12:19:44 | inbound | image | Mauro — prednja |
| 544 | 12:19:54 | inbound | image | Mauro — stražnja (procjena) |
| 545 | 12:20:06 | outbound | interactive | *Jeste li poslali sve dokumente?* |
| 546 | 12:20:08 | inbound | image | Veronika — prednja (procjena) |
| 547 | 12:20:16 | inbound | image | Veronika — stražnja (procjena) |
| 548 | 12:20:21 | inbound | interactive | **Da** (ignorirano u tom trenutku) |

---

## Problem 1 — confirm flow (slika umjesto Da)

### Simptomi

- Gost dobije Ja/Ne pitanje, pošalje **još slika** umjesto odgovora, zatim klikne **Da** — sustav ne odgovori.
- Sesija ostane u `collecting`, job u `queued` / kasnije `applied` samo djelomično.

### Root cause

1. Nova slika nakon Ja/Ne resetira sesiju s `awaiting_confirm` → `collecting`.
2. Handler za **Da** prihvaćao je odgovor samo u `awaiting_confirm` → `no_active_confirm`.
3. Nema ack poruke niti OCR previewa prije ponovnog pitanja.

### Fix u kodu

Plan *WhatsApp confirm-during-batch* (2026-06-22):

- ack gostu kad stigne slika tijekom confirm faze;
- OCR preview nakon 10 s tišine, zatim ponovno Ja/Ne;
- **Da** prihvaćen i u `collecting` ako je `prompt_count > 0`;
- kolona `confirm_interrupted_at` na sesiji.

Vidi [`whatsapp-operator-toni-runbook.md`](./whatsapp-operator-toni-runbook.md) (guest recovery).

### Timeline (UTC)

```
12:18  Auto check-in → upit za dokumente
12:19  2 slike
12:20:06  Ja/Ne confirm prompt
12:20:08, 12:20:16  2 slike (sesija → collecting)
12:20:21  Klik Da → skipped (no_active_confirm)
12:23  Ručni finalize sesije #13
```

---

## Problem 2 — pogrešan guest match (OCR / apply)

### Simptomi (recepcija)

- Na rezervaciji booker je **Mauro Di Liddo** (`Guest` #2186), drugi slot prazan / „Novi gost” (#2187).
- Nakon finalize-a OCR podaci su završili na **drugom** gostu (#2187) kao **MAURO DILIDDO**.
- **Veronika DUDA** (2. osoba u OCR-u) nije bila matchana ni na jedan slot.

### Root cause

| Čimbenik | Detalj |
|----------|--------|
| OCR / MRZ | Prezime iz dokumenta: **`DILIDDO`** (spojeno, velika slova) |
| Rezervacija | Booker: **`Di Liddo`** (razmak, mixed case) |
| Matcher | Nema fuzzy matcha booker ↔ OCR → person 0 ide na **prvi slobodni slot** (`unfilled_slot` → #2187) |
| Person 1 | VERONIKA DUDA → `guest_id: null`, `confidence: none` |

OCR je ispravno pročitao **4 slike / 2 osobe**:

```
person 0: MAURO DILIDDO  doc 116437058  images 0–1
person 1: VERONIKA DUDA  doc 119360317  images 2–3
```

Apply (prije korekcije):

```
Guest 2186  Mauro Di Liddo     — prazan (nema doc)
Guest 2187  MAURO DILIDDO      — IdDoc #155, scan log #99  ← pogrešan slot
Veronika    — unmatched
```

Povezano: [ocr-multi-guest-rules.md](./ocr-multi-guest-rules.md) — booker vs companion slot, fuzzy ime.

### Ručna korekcija (2026-06-22, bez obavijesti gostu)

Izvršeno u Django shellu — **nema** WhatsApp poruka gostu.

**Koraci:**

1. `IdDocument` #155 i `DocumentScanLog` #99 prebačeni s #2187 na **#2186** (Mauro Di Liddo).
2. Polja gosta #2186 popunjena iz OCR person 0, ime zadržano **`Mauro` / `Di Liddo`** (booker spelling).
3. Slot #2187 očišćen, zatim `_apply_person_to_guest` za OCR person 1 (Veronika).
4. `DocumentIntakeJob` #81 — `matches`, `applied_result` ručno usklađeni; status `applied`.

**Stanje nakon korekcije:**

| Guest | Ime | Doc | IdDoc | Scan log |
|-------|-----|-----|-------|----------|
| #2186 | Mauro Di Liddo | 116437058 | #155 | #99 |
| #2187 | VERONIKA DUDA | 119360317 | novi | #100 |

`evaluate_completeness`: **kompletno** (oba odrasla, prednja + stražnja).

#### Shell (referenca — već izvršeno)

```python
from django.db import transaction
from datetime import date
from apps.reservations.models import Guest, IdDocument, DocumentScanLog, DocumentIntakeJob, Reservation
from apps.reservations.document_intake_service import _apply_person_to_guest

RES_ID, JOB_ID = 799, 81
MAURO_ID, VERONIKA_ID = 2186, 2187

with transaction.atomic():
    job = DocumentIntakeJob.objects.prefetch_related("images").get(pk=JOB_ID)
    reservation = Reservation.objects.get(pk=RES_ID)
    mauro = Guest.objects.get(pk=MAURO_ID)
    slot2 = Guest.objects.get(pk=VERONIKA_ID)
    p0, p1 = job.ocr_result["persons"]
    images = list(job.images.order_by("sort_order", "id"))

    IdDocument.objects.filter(pk=155).update(guest_id=MAURO_ID)
    DocumentScanLog.objects.filter(pk=99).update(guest_id=MAURO_ID)

    mauro.first_name, mauro.last_name = "Mauro", "Di Liddo"
    mauro.document_number = p0["document_number"]
    mauro.date_of_birth = date.fromisoformat(p0["date_of_birth"])
    mauro.date_of_expiry = date.fromisoformat(p0["date_of_expiry"])
    # ... ostala polja iz OCR person 0 ...
    mauro.save()

    slot2.id_documents.all().delete()
    # ... reset slot2 polja ...
    veronica_result = _apply_person_to_guest(
        person=p1, person_index=1, guest=slot2,
        reservation=reservation, images=images, device_id="whatsapp",
    )
    # ... update job.matches / applied_result ...
```

---

## Recovery (generički)

### Zaglavljen confirm flow

```bash
docker compose exec django python manage.py reconcile_guest_document_batches \
  --reservation-id 799 --apply
```

### Ručno finalize sesije

```python
from apps.integrations.whatsapp.whatsapp_document_batch import finalize_whatsapp_document_batch
from apps.reservations.models import WhatsAppDocumentBatchSession

session = WhatsAppDocumentBatchSession.objects.get(pk=13)
finalize_whatsapp_document_batch(session.pk)
```

---

## Otvoreno (out of scope ovog incidenta)

- **Fuzzy match** booker imena (`Di Liddo`) ↔ MRZ (`DILIDDO`) — zaseban ticket na matcheru.
- **`whatsapp_autocheckin_session_lost=True`** ostao nakon engagementa — kozmetički flag u recepciji.

---

## Povezano

- [whatsapp-operator-toni-runbook.md](./whatsapp-operator-toni-runbook.md)
- [ocr-multi-guest-rules.md](./ocr-multi-guest-rules.md)
- [whatsapp-checkin-template.md](./whatsapp-checkin-template.md)
