# OCR batch — pravila za više gostiju

Operativna pravila za WhatsApp / Hospira batch OCR (`document-intake` API). Ažurirano nakon slučaja **rezervacija #51** (lipanj 2026).

**Povezano:** [id-document-import.md](../development/id-document-import.md), [ai-runbook-ocr-checkin-evisitor-2026-06.md](../operations/ai-runbook-ocr-checkin-evisitor-2026-06.md)

---

## Što sustav radi automatski (nakon popravka)

1. **Batch OCR** — do 20 slika u jednom jobu; LLM vraća `persons[]` (uparene prednja/stražnja strana).
2. **Matching** — po osobi:
   - prvo **ime** (fuzzy match na gosta rezervacije),
   - zatim **prazan slot** — preferira **„Novi gost”** placeholder, ne primary booker bez dokumenta,
   - unutar batcha **ne dodjeljuje isti guest_id** dvjema osobama.
3. **auto_apply** — primjenjuje se kad je kandidat jedinstven, ili kad je cijeli batch očito na **jednu rezervaciju** (name match na primary + suputnici na istoj rezervaciji).
4. **Guest slotovi pri apply** — `max(adults_count, persons_count, broj OCR osoba)`; ako treba, kreira se dodatni **Novi gost**.
5. **Re-apply** — ponovni `POST .../apply/` na već primijenjen job **preskače** goste koji su već bili u `applied_result` (npr. samo nedostajući suputnici).

eVisitor se **ne šalje automatski** — i dalje ručno / gumb u Hospiri.

---

## Checklist recepcije (normalan flow)

1. Gost pošalje fotke (WhatsApp share → Hospira).
2. Hospira: batch upload → process → apply (prazan body je OK).
3. U eVisitor listi provjeri:
   - broj gostiju = **Osobe** na rezervaciji (`persons_count`),
   - nema **„Novi gost”** s popunjenim dokumentom negdje drugdje,
   - djeca &lt; 18: eVisitor „Nije potrebno” ako je DOB prepoznat.
4. Po potrebi **Prijavi u eVisitor** po odraslom gostu.

---

## Kad nešto fali — brza dijagnostika

```bash
docker exec stay_django python manage.py shell -c "
from apps.reservations.models import Reservation, DocumentIntakeJob
r = Reservation.objects.get(pk=REZ_ID)
print('persons', r.persons_count, 'adults', r.adults_count, 'guests', r.guests.count())
for g in r.guests.order_by('-is_primary','id'):
    print(g.id, g.name, g.document_number or '-')
j = DocumentIntakeJob.objects.order_by('-id').first()
for m in j.matches or []:
    print(m.get('person_index'), m.get('person_name'), 'auto', m.get('auto_apply'), 'guest', m.get('guest_id'))
"
```

| Simptom | Vjerojatni uzrok | Akcija |
|--------|------------------|--------|
| Samo primary ažuriran | Stari kod / apply prije process DONE | Restart django, ponovi apply na job |
| `persons` u OCR &lt; slika/2 | Loše uparivanje front/back | Ručni OCR po runbooku §2 |
| Nedostaje 3. gost | `persons_count` &gt; broj guest redova | Ponovi apply (kreira slot) ili `ensure_guest_slots` |
| `auto_apply=False` za sve | Više rezervacija u prozoru s praznim slotovima | Apply s ručnim `persons[]` selekcijama |

### Ponovni apply na postojeći job

```bash
docker exec stay_django python manage.py shell -c "
from apps.reservations.document_intake_service import apply_document_intake_job
from apps.reservations.models import DocumentIntakeJob
job = DocumentIntakeJob.objects.get(pk=JOB_ID)
applied = apply_document_intake_job(job.pk)
print('applied', len(applied), applied)
"
```

---

## Ručni apply s odabirom (kad je više rezervacija u prozoru)

```http
POST /api/v1/reception/document-intake/jobs/{job_id}/apply/
{
  "persons": [
    {"person_index": 0, "reservation_id": 51, "guest_id": 1057},
    {"person_index": 1, "reservation_id": 51, "guest_id": 1939},
    {"person_index": 2, "reservation_id": 51, "guest_id": NOVI_GUEST_ID}
  ]
}
```

---

## Pravila za djecu i persons_count

- Import i placeholderi: **`adults_count`** pri uvozu, **`persons_count`** pri OCR apply.
- Dijete (npr. 16 god.) **treba guest red** ako je poslao osobnu — koristi `persons_count`.
- eVisitor: &lt; 18 na dan check-ina → nije obavezno; guest red i dokument i dalje korisni za evidenciju.

---

## Datoteke u kodu

| Datoteka | Uloga |
|----------|--------|
| `backend/apps/reservations/document_intake_match.py` | Matching + auto_apply |
| `backend/apps/reservations/guest_slots.py` | `ensure_guest_slots_for_intake()` |
| `backend/apps/reservations/document_intake_service.py` | process / apply |
| `backend/apps/api/reception_document_intake_views.py` | API |

Nakon promjena Python koda: `./scripts/deploy.sh` ili `docker compose restart django`.

### eVisitor — obavezna polja

| Polje | Uvjet |
|-------|--------|
| **Spol** | Obavezan za odrasle. Njemačka osobna **nema spol** na kartici ni u MRZ (`<`) — unesite **M/F ručno** u Hospiri prije prijave. |
| **Adresa** | Format **`Grad, ulica`** (bez poštanskog broja u gradu). Npr. `94036 PASSAU, ...` → `PASSAU, WILHELM-PÖLL-STRAGE 7`. |

Sync nakon OCR:

```bash
docker exec stay_django python manage.py sync_guest_evisitor_fields --reservation-id 51
```

Spol iz MRZ-a (kad postoji M/F) i normalizacija adrese rade automatski pri novom OCR apply-u.

### Avatar (face crop)

Automatski crop koristi **OpenCV face detection** na prednjoj strani osobne; LLM `face_bbox` se ignorira ako je generički placeholder.

Ponovni crop postojećih gostiju:

```bash
docker exec stay_django python manage.py recrop_guest_faces --reservation-id 51
docker exec stay_django python manage.py recrop_guest_faces --guest-id 1057 --dry-run
```
