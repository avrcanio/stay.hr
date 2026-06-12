# WhatsApp operator flow — Toni (document intake)

Operativna uputa za slanje fotografija dokumenata gosta s mobitela na poslovni WhatsApp broj.

**Poslovni broj (360dialog):** `+385 97 678 9626`  
**Ne koristiti:** stari `+385 99 838 8513` (WhatsApp Business app — ne ide u Hospiru).

**Whitelist operatori:** Toni Šupe `+385998388513`, Ante Vrcan `+385976713511`  
Seed: `python manage.py seed_uzorita_whatsapp_operators --tenant-id 2`

---

## Koraci (svaki check-in)

1. Otvori chat s **`+385 97 678 9626`**.
2. Pošalji **fotografiju putovnice/CI** (cijela stranica s podacima, bez bljeskalice).
   - Može više slika (više gostiju) — pošalji jednu po jednu ili u nizu.
3. **Pričekaj ~10 sekundi** — sustav šalje:
   > „Primljeno X slika. Pritisnite **Check-in** ako ste gotovi.“
4. Pritisni gumb **Check-in** (ili pošalji tekst `check in`).
5. Ako sustav ne prepozna rezervaciju automatski → pošalji **`#863`** ili **Booking kod** (npr. `5952655431`).
6. Potvrdi **Da** ako pita jesu li svi dokumenti poslani.
7. Toni dobije potvrdu: check-in + eVisitor (kad je dan dolaska).

---

## Što se događa u pozadini

```
Toni → slika → webhook → DocumentIntakeJob
       → (10 s) → „Primljeno X slika“ + Check-in gumb
       → Check-in → OCR → match rezervacija → apply + eVisitor
```

---

## Uobičajeni problemi

| Simptom | Uzrok | Rješenje |
|---------|-------|----------|
| Nema odgovora „Primljeno X slika“ | Celery worker nije registrirao task (restart worker) ili worker down | `docker compose restart celery-worker` |
| „Nema aktivnih slika“ | Check-in prije slike | Prvo slika, pa Check-in |
| „Nisam pronašao rezervaciju“ | OCR/match neuspjeh | Pošalji `#<id>` ili booking kod |
| Chat na **8388513** | Krivi broj | Prebaci na **976789626** |

---

## Ručni recovery (recepcija / admin)

Ako je slika stigla ali flow stao:

```bash
# Pronađi job
docker compose exec django python manage.py shell -c "
from apps.reservations.models import DocumentIntakeJob
for j in DocumentIntakeJob.objects.filter(source='whatsapp_operator').order_by('-pk')[:5]:
    print(j.pk, j.status, j.reservation_id, j.images.count())
"

# Replay (dry-run prvo)
docker compose exec django python manage.py complete_operator_document_job \
  --job-id <JOB_ID> --reservation-id <RES_ID> --operator-wa-id 385998388513 --dry-run

# Apply
docker compose exec django python manage.py complete_operator_document_job \
  --job-id <JOB_ID> --reservation-id <RES_ID> --operator-wa-id 385998388513
```

---

## Incident 2026-06-12 — Mile Šujić (#863)

| Stavka | Vrijednost |
|--------|------------|
| Inbound | `WhatsAppMessage` #261, wa_id `385998388513`, 07:47 CEST |
| Job | #50, 1 slika putovnice |
| Uzrok | Celery task `operator_collect_quiet_elapsed` nije bio registriran → Toni nije dobio „Primljeno 1 sliku“ |
| Fix | Import u `tasks.py` + restart `celery-worker`; replay `complete_operator_document_job --job-id 50 --reservation-id 863` |

Povezano: [guest-messages-channels.md](./guest-messages-channels.md), [whatsapp-checkin-template.md](./whatsapp-checkin-template.md)
