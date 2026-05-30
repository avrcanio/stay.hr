# ID dokumenti — spremanje slika i parsiranje podataka

Operativni vodič za ručni unos (WhatsApp fotke, Booking XLS) u stay.hr. Odgovara praksi korištenoj u recepciji (svibanj 2026).

**Media root na serveru:** `/opt/stacks/stay.hr/data/media` (u Dockeru: `/app/backend/media`)

---

## 1. Struktura mapa

| Tip | Mapa | Primjer imena |
|-----|------|----------------|
| Osobna — prednja | `id_documents/front/` | `200526_1133_idf.jpg` |
| Osobna — stražnja | `id_documents/back/` | `200526_1133_idb.jpg` |
| Putovnica (cijela stranica) | `id_documents/passports/` | `200526_1128_pass.jpg` |
| Avatar (portret) | `id_documents/faces/` | `200526_1133_idf.jpg` |
| Potpis (NFC/OCR app) | `id_documents/signatures/` | `guest_{id}_face.jpg` (legacy) |

### Konvencija imena (ručni unos)

```
ddmmyy_{guest_id}_{tip}.jpg
```

| Sufiks | Značenje |
|--------|----------|
| `idf` | ID front (prednja strana osobne) |
| `idb` | ID back (stražnja strana osobne) |
| `pass` | Passport (biodata stranica putovnice) |

- `ddmmyy` = datum obrade (npr. 20.05.2026 → `200526`)
- `guest_id` = primarni ključ `Guest` u bazi (npr. `1133`)

**API upload** (Hospira „Slikaj dokument”) koristi drugačiji timestamp u kodu: `document_photo_filename()` → `DDMMYYHHMM_{guest_id}_pass.jpg` ili `_frontID.jpg` / `_backID.jpg` — vidi `backend/apps/reservations/document_photo_storage.py`.

---

## 2. Modeli u bazi

### `Guest` — podaci s dokumenta

Parsirani podaci idu direktno na gosta:

| Polje | Primjer |
|-------|---------|
| `first_name`, `last_name`, `name` | Lauriane / Saulnier |
| `document_number` | `150742301041` |
| `nationality` | `FR` (ISO-2) |
| `sex` | `M` / `F` |
| `date_of_birth` | `1996-07-20` |
| `date_of_issue` | `2017-04-21` |
| `date_of_expiry` | `2032-04-20` |
| `issuing_authority` | `PRÉFECTURE DE LA LOIRE (42)` |
| `address` | `2 RUE MONTESQUIEU, UNIEUX (42)` |
| `document_type` | `Putovnica` ili `Osobna iskaznica` |
| `document_code` | `P` (passport) / `ID` (osobna) |
| `document_country_iso2` / `iso3` | `BE` / `BEL` |
| `mrz_raw_text` | dvije MRZ linije (novi red) |
| `mrz_verified` | `true` ako je MRZ čitljiv |

Dodatno (nema zasebnog polja): mjesto rođenja, visina → `IdDocument.extracted_payload` JSON.

### `IdDocument` — veza na slike

Jedan zapis po skeniranju; polja:

| Polje | Putanja (relativno na MEDIA_ROOT) |
|-------|-----------------------------------|
| `front_photo` | `id_documents/front/200526_{guest_id}_idf.jpg` |
| `back_photo` | `id_documents/back/200526_{guest_id}_idb.jpg` |
| `face_photo` | `id_documents/faces/200526_{guest_id}_idf.jpg` |
| `image_path` | ista kao `front_photo` (referenca) |
| `extracted_payload` | `{"source": "manual_ocr", ...}` |

Za putovnicu: samo `front_photo` → `id_documents/passports/...`, `document_type` na gostu = `Putovnica`.

**Avatar u UI:** `Guest.face_photo_url` → API čita `IdDocument.face_photo` (zadnji dokument s fotkom).

---

## 3. Postupak: osobna iskaznica (prednja + stražnja)

### 3.1 Ulaz

- Prednja: fotka biodata + portret (npr. francuska CNI, HR osobna)
- Stražnja: adresa, datum izdavanja, valjanost
- Opcionalno: zasebni crop portreta za avatar (korisnik pošalje u chat)

### 3.2 OCR

Na hostu (Tesseract):

```bash
tesseract "/path/to/front.jpg" stdout -l fra+eng
tesseract "/path/to/back.jpg" stdout -l fra+eng
```

Provjeri i MRZ na dnu prednje strane (pouzdanije za broj dokumenta i datume).

### 3.3 Mapiranje polja

**Prednja strana**

- Broj dokumenta, ime, prezime, spol, datum rođenja, državljanstvo
- MRZ: `P<...` = putovnica, `ID<...` = osobna

**Stražnja strana**

- Adresa — ⚠️ **eVisitor:** upisati kao **`Grad, ulica`** (npr. `Osijek, Dubrovačka 30`), ne ulicu pa grad. Vidi [evisitor-adresa-res-190-2026-05-30.md](../operations/evisitor-adresa-res-190-2026-05-30.md).
- `délivrée le` / datum izdavanja
- `valable jusqu'au` / datum isteka  
  ⚠️ Paziti na odsjaj na foliji — godina može biti pogrešno pročitana (npr. 2025 vs 2030). Za FR CNI izdanu 2017. često je valjanost **15 godina**.

### 3.4 Spremi datoteke

```bash
GUEST_ID=1610
DATE=200526   # dan obrade

cp front-source.jpg "data/media/id_documents/front/${DATE}_${GUEST_ID}_idf.jpg"
cp back-source.jpg  "data/media/id_documents/back/${DATE}_${GUEST_ID}_idb.jpg"
chown 1000:1000 data/media/id_documents/front/${DATE}_${GUEST_ID}_idf.jpg \
                 data/media/id_documents/back/${DATE}_${GUEST_ID}_idb.jpg
```

### 3.5 Avatar iz prednje strane (Pillow)

Izrez portreta s lijeve trećine kartice, kvadrat 256×256:

```python
from PIL import Image
front = Image.open("front.jpg").convert("RGB")
w, h = front.size
box = (int(w * 0.02), int(h * 0.12), int(w * 0.34), int(h * 0.88))
portrait = front.crop(box)
side = portrait.size[0]
top = max(0, min(int((portrait.size[1] - side) * 0.05), portrait.size[1] - side))
face = portrait.crop((0, top, side, top + side)).resize((256, 256))
face.save(f"data/media/id_documents/faces/{DATE}_{GUEST_ID}_idf.jpg", "JPEG", quality=92)
```

Korisnik može poslati bolji crop u chat → prepisati isti path `faces/..._idf.jpg`.

### 3.6 Upis u Django

```bash
docker exec stay_django python manage.py shell
```

```python
from datetime import date
from apps.reservations.models import Guest, IdDocument, Reservation

# Novi gost na rezervaciji (suputnik)
r = Reservation.objects.get(pk=128)
guest = Guest.objects.create(
    tenant=r.tenant,
    reservation=r,
    first_name="Florian",
    last_name="Renaudier",
    name="Florian Renaudier",
    nationality="FR",
    is_primary=False,  # prvi gost na rezervaciji = True
)
guest.document_number = "170442302577"
guest.sex = "M"
guest.date_of_birth = date(1996, 5, 5)
guest.date_of_issue = date(2017, 4, 21)
guest.date_of_expiry = date(2032, 4, 20)
guest.issuing_authority = "PRÉFECTURE DE LA LOIRE (42)"
guest.address = "2 RUE MONTESQUIEU, UNIEUX (42)"
guest.document_type = "Osobna iskaznica"
guest.document_code = "ID"
guest.document_country_iso2 = "FR"
guest.document_country_iso3 = "FRA"
guest.mrz_raw_text = "IDFRA...\n170442..."
guest.mrz_verified = True
guest.save()

doc = IdDocument.objects.create(
    guest=guest,
    image_path="id_documents/front/200526_1610_idf.jpg",
    extracted_payload={"source": "manual_ocr", "place_of_birth": "FIRMINY"},
)
doc.front_photo.name = "id_documents/front/200526_1610_idf.jpg"
doc.back_photo.name = "id_documents/back/200526_1610_idb.jpg"
doc.face_photo.name = "id_documents/faces/200526_1610_idf.jpg"
doc.save()
```

---

## 4. Postupak: putovnica (jedna stranica)

- Izvor: jedna fotka biodata stranice
- Spremi: `id_documents/passports/ddmmyy_{guest_id}_pass.jpg`
- `document_type` = `Putovnica`, `document_code` = `P`
- MRZ obavezno ako je čitljiv
- Avatar: crop portreta s lijeve strane → `faces/ddmmyy_{guest_id}_idf.jpg` ili korisnički crop

Primjer (gost #1128, belgijska putovnica): `200526_1128_pass.jpg`

---

## 5. Više gostiju na jednoj rezervaciji

1. Rezervacija iz Booking XLS-a, Smoobu ili Channexa → **primarni** `Guest` (booker), `is_primary=True`.
2. Ako je `adults_count` veći od broja imenovanih gostiju, import automatski dodaje placeholder goste **`Novi gost`** (`is_primary=False`) — spremni za check-in i eVisitor.
3. **Djeca** se ne dodaju automatski; placeholderi se računaju samo prema `adults_count`.
4. Svaki gost ima vlastiti `guest_id` u imenu datoteka i vlastiti `IdDocument`.

Provjera:

```bash
docker exec stay_django python manage.py shell -c "
from apps.reservations.models import Reservation
r = Reservation.objects.get(pk=128)
for g in r.guests.order_by('-is_primary', 'id'):
    print(g.id, g.name, g.is_primary, g.document_number)
"
```

---

## 6. Booking.com XLS → rezervacija

Vidi **[booking-xls-import.md](./booking-xls-import.md)** — tri načina uvoza (preskoči / dopuni prazno / prepiši), skripta, primjeri i mapiranje polja.

---

## 7. Push notifikacije (nova rezervacija)

- Signal: `post_save` na `Reservation` (samo `created=True`)
- Task: `apps.core.tasks.notify_new_reservation`
- Tokeni: `ApiApplication.fcm_token` po tenantu (Hospira `PUT /api/v1/app/fcm-token`)

Provjera tokena:

```bash
docker exec stay_django python manage.py shell -c "
from apps.core.notifications import tenant_fcm_tokens
print(tenant_fcm_tokens(2))
"
```

---

## 8. Primjeri iz produkcije (2026-05-20)

| Gost ID | Rezervacija | Dokument | Datoteke |
|---------|-------------|----------|----------|
| 1128 | — | BE putovnica | `200526_1128_pass.jpg`, avatar `faces/200526_1128_idf.jpg` |
| 1133 | 128 | FR osobna (Lauriane) | `200526_1133_idf.jpg`, `200526_1133_idb.jpg` |
| 1610 | 128 | FR osobna (Florian, suputnik) | `200526_1610_idf.jpg`, `200526_1610_idb.jpg` |

---

## 9. Checklist prije eVisitora

- [ ] `document_number`, `date_of_birth`, `nationality` (ISO-2)
- [ ] `document_type` i valjanost (`date_of_expiry` u budućnosti)
- [ ] Prednja + stražnja slika za osobnu; putovnica samo jedna strana
- [ ] Avatar (`face_photo`) za prikaz u recepciji
- [ ] Svi gosti na rezervaciji imaju upisan profil

---

## 10. Povezani kod i API

| Što | Gdje |
|-----|------|
| Modeli | `backend/apps/reservations/models.py` |
| Upload imena (app) | `backend/apps/reservations/document_photo_storage.py` |
| Face URL | `backend/apps/reservations/face_photo.py` |
| OCR ingest (app) | `backend/apps/api/reception_views.py` → `DocumentScanView` |
| Booking XLS | [booking-xls-import.md](./booking-xls-import.md) |
| Upload fotografija (API) | `POST .../guests/{id}/document-photos/` |

Legacy Uzorita referenca: `/opt/stacks/uzorita/rooms/code/docs/operations/` (booking-ingest, OCR runbook).
