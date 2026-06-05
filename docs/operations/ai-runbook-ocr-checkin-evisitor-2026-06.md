# AI runbook: ručni OCR, check-in i eVisitor (lipanj 2026)

Operativni zapis slučajeva koje je agent obavio na produkciji **stay.hr** (WhatsApp fotke → medij → `Guest` / `IdDocument` → eVisitor). Namijenjeno budućem AI agentu i recepciji.

**Povezano:** [id-document-import.md](../development/id-document-import.md) (struktura mapa, modeli), [ocr-multi-guest-rules.md](./ocr-multi-guest-rules.md) (batch OCR, više gostiju), [evisitor-adresa-res-190-2026-05-30.md](./evisitor-adresa-res-190-2026-05-30.md) (format adrese).

**Media root:** `/opt/stacks/stay.hr/data/media` · **Django:** `docker exec stay_django python manage.py shell`

---

## 1. Brzi postupak (checklist)

1. **Identificiraj rezervaciju i goste** — `Guest` ID, `is_primary`, placeholder „Novi gost”.
2. **OCR sve ulazne fotke** — ne pretpostavljaj redoslijed; **upari prednju/stražnju MRZ-om** (vidi §2).
3. **Razdvoji dokumente po osobi** — putovnica ≠ osobna drugog gosta na istoj rezervaciji.
4. **Kopiraj medij** — `ddmmyy_{guest_id}_idf.jpg` / `_idb.jpg` / `_pass.jpg`.
5. **Avatar** — crop iz chata (PNG→JPEG na **hostu**, Pillow); ne iz Docker kontejnera (`/root/.cursor/...` nije vidljiv u kontejneru).
6. **`chown 1000:1000`** na nove datoteke u `data/media/id_documents/`.
7. **Django shell** — update `Guest` + `IdDocument` (bez `tenant` u `IdDocument.objects.create()`).
8. **Check-in rezervacije** — samo ako još nije `checked_in`.
9. **eVisitor** — `submit_guest_checkin(guest)` za svakog odraslog; adresa **`Grad, ulica`**.
10. **Provjera** — `evisitor_status=sent`, `face_photo.url`.

---

## 2. OCR i uparivanje strana (ključna lekcija)

### Problem

WhatsApp šalje 4+ fotke bez jasnog redoslijeda. Pogrešno uparivanje (npr. stražnja osobne A + prednja osobne B) daje krive MRZ podatke.

### Rješenje: MRZ na stražnjoj strani

Njemačka / EU osobna (TD1): MRZ je u **donjih ~35–40%** stražnje strane (3 linije).

```bash
# Osnovni OCR prednje
tesseract "/path/to/front.jpg" stdout -l deu+eng --psm 6

# Stražnja — ako prazan, crop + autocontrast (Python/Pillow) pa:
tesseract crop.png stdout -l deu+eng --psm 6
# ili whitelist za MRZ:
tesseract crop.png stdout -l eng --psm 6 \
  -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<
```

**Python crop (donja trećina):**

```python
from PIL import Image, ImageOps
im = Image.open(path).convert("L")
w, h = im.size
crop = im.crop((0, int(h * 0.55), w, h))
crop = ImageOps.autocontrast(crop)
```

**Uparivanje:** stražnja s `FISCHER<<HANS<PETER` ide uz prednju s `FISCHER` / `HANS PETER`; stražnja s `OTTO<<ELKE<DOROTHEE` uz prednju s `OTTO` / `GEB. MAURER`.

### Primjer pogreške (Fischer/Otto, 01.06.2026.)

| Pogrešna pretpostavka | Ispravno (MRZ) |
|----------------------|----------------|
| `(1)` = Fischer stražnja | `(1)` = **Otto** stražnja (`OTTO<<ELKE<DOROTHEE`) |
| `(3)` = Otto stražnja | `(3)` = **Fischer** stražnja (`FISCHER<<HANS<PETER`) |

### Jezici Tesseract

| Dokument | `-l` |
|----------|------|
| Njemačka osobna | `deu+eng` |
| Poljska osobna / putovnica | `pol+eng` |
| FR osobna | `fra+eng` |

Ako `deu` nedostaje na hostu, `eng` često i dalje čita MRZ.

---

## 3. eVisitor adresa

Mapper: `backend/apps/integrations/evisitor/mapper.py` — `CityOfResidence` / `CityOfBirth` = **prvi segment prije zareza** u `guest.address`.

| Ispravno | Krivo |
|----------|-------|
| `Markdorf, Grönbrunnstraße` | `Grönbrunnstraße, Markdorf` |
| `Krailling, Elisenstr. 16` | `Elisenstr. 16, Krailling` |
| `Stuttgart, -` (fallback ako stražnja nečitljiva) | prazno |

Ako API vrati HTTP 400 na grad: ispravi adresu, ponovi s `force_retry=True` (vidi [evisitor-adresa-res-190](./evisitor-adresa-res-190-2026-05-30.md)).

---

## 4. Django — tipični upisi

### Putovnica (jedan gost, jedna biodata stranica)

- `document_type` = `Putovnica`, `document_code` = `P`
- `IdDocument.image_path` i `front_photo` → `id_documents/passports/ddmmyy_{id}_pass.jpg`
- Osobna drugog gosta **ne** stavljati na isti `Guest`

### Osobna (prednja + stražnja)

- `document_type` = `Osobna iskaznica`, `document_code` = `ID`
- `front_photo` → `front/`, `back_photo` → `back/`

### eVisitor

```python
from apps.reservations.models import Guest
from apps.integrations.evisitor.service import submit_guest_checkin
from apps.integrations.evisitor.exceptions import EvisitorValidationError, EvisitorApiError

guest = Guest.objects.get(pk=GUEST_ID)
sub = submit_guest_checkin(guest)  # status sent, response {'ok': True}
```

Country lookup HTTP 400 u logu je **upozorenje**, ne blokira check-in (viđeno u produkciji).

### Provjera

```bash
docker exec stay_django python manage.py shell -c "
from apps.reservations.models import Guest, IdDocument
g = Guest.objects.get(pk=GUEST_ID)
d = IdDocument.objects.filter(guest=g).first()
print(g.name, g.document_number, g.address, g.evisitor_status)
print(d.face_photo.url if d and d.face_photo else None)
"
```

---

## 5. Slučajevi iz prakse (01.–01.06.2026.)

### 5.1 Hans Günther Nolleweit — rez. #115, gost #1120

| | |
|--|--|
| **Rezervacija** | #115 · R3 · 2026-05-31 → 2026-06-01 |
| **Dokument** | DE Personalausweis `LF9L8KH2R` |
| **Fotke** | `.wp_photos/WhatsApp Image 2026-05-31 at 18.56.48.jpeg` (prednja), `18.56.54.jpeg` (stražnja) |
| **Medij** | `310526_1120_idf.jpg`, `310526_1120_idb.jpg` |
| **Avatar** | Chat PNG → `310526_1120_idf.jpg` (ne auto-crop s prednje) |
| **Adresa eVisitor** | `Krailling, Elisenstr. 16` |
| **MRZ** | `IDD<<LF9L8KH2R4...` / `6201201<3111231D...` / `NOLLEWEIT<<HANS<GUENTHER` |
| **eVisitor** | `sent` (prvi pokušaj) |

Check-in: `expected` → `checked_in`.

---

### 5.2 Marcin Kreft + Pawel Jan Szczypior — rez. #810

**Dva gosta, dva dokumenta — ne miješati.**

| Gost | ID | Dokument | Fotke |
|------|-----|----------|-------|
| Marcin Piotr Kreft (primarni) | #2212 | Putovnica `ES2977513` | `09.17.15.jpeg` |
| Pawel Jan Szczypior (suputnik) | #2213 | Osobna `DAA503979` | `09.11.09 (1).jpeg` prednja, `09.11.09.jpeg` stražnja |

| Gost | Medij prefiks | Avatar |
|------|---------------|--------|
| #2212 | `010626_2212_pass.jpg` + face | Chat portret putovnice |
| #2213 | `010626_2213_idf/idb` | Chat crop (kasnije zamijenjen boljim PNG-om) |

**Kreft:** DOB 1977-01-30, Gdynia, PESEL na putovnici `77013005258`, adresa `Gdynia, -`.

**Szczypior:** DOB 1995-05-05, Wejherowo, MRZ `SZCZYPIOR<<PAWEL<JAN`.

**Lekcija:** Prednja PL osobne imala pogrešan PESEL u lošem OCR-u (`95050504451`) — **pouzdati putovnicu/MRZ**, ne front osobne drugog formata.

Oba: `evisitor_status=sent`. Rezervacija već `checked_in`.

---

### 5.3 Hans Peter Fischer + Elke Dorothee Otto — rez. #810 (isti booking, drugi par dokumenata)

Booking booker: „Peter Fischer” → pravo ime s osobne: **Hans Peter Fischer** (#2188).

| Datoteka | Gost | Strana |
|----------|------|--------|
| `10.10.37.jpeg` | Fischer #2188 | prednja |
| `10.10.37 (3).jpeg` | Fischer #2188 | stražnja |
| `10.10.37 (2).jpeg` | Otto #2189 | prednja |
| `10.10.37 (1).jpeg` | Otto #2189 | stražnja |

| Gost | ID | Dokument | Ključni podaci |
|------|-----|----------|----------------|
| Hans Peter Fischer | #2188 | `L01CRF0LP4` | rođ. 1961-04-01 Stuttgart, istek 2028-10-18, M |
| Elke Dorothee Otto | #2189 | `L02COBJVM3` | rođ. 1967-08-13 Meersburg, izd. 2018-11-30 Markdorf, F |

**Adrese eVisitor:** `Stuttgart, -` · `Markdorf, Grönbrunnstraße` (OCR stražnje Otto: `GRONBRAUN` + `88677` + `MARKDORF`).

**Avatari:** chat PNG `6abdee4d...` (Fischer), `0bcd3379...` (Otto) → `010626_2188_idf.jpg`, `010626_2189_idf.jpg`.

**IdDocument:** #40 (Fischer), #41 (Otto). Oba `evisitor sent`.

---

## 6. Avatar — operativno

```bash
python3 -c "
from PIL import Image
Image.open('/root/.cursor/projects/.../image-XXX.png').convert('RGB').save(
    '/opt/stacks/stay.hr/data/media/id_documents/faces/010626_GUEST_idf.jpg',
    'JPEG', quality=92)
"
chown 1000:1000 /opt/stacks/stay.hr/data/media/id_documents/faces/010626_GUEST_idf.jpg
```

`IdDocument.face_photo.name` već pokazuje na isti path — **dovoljno prepisati datoteku** bez DB updatea.

Za crop s prednje osobne (ako nema chat priloga): lijeva ~34% kartice, kvadrat 256×256 — vidi [id-document-import.md §3.5](../development/id-document-import.md).

---

## 7. Mapiranje ulaznih fotki (.wp_photos)

Tipični izvori:

```
/opt/stacks/stay.hr/.wp_photos/WhatsApp Image YYYY-MM-DD at HH.MM.SS.jpeg
/opt/stacks/stay.hr/.wp_photos/WhatsApp Image YYYY-MM-DD at HH.MM.SS (N).jpeg
```

Chat avatari (Cursor):

```
/root/.cursor/projects/opt-stacks-stay-hr/assets/c__Users_..._images_image-{uuid}.png
```

---

## 8. Česte greške (izbjegavati)

| Greška | Posljedica |
|--------|------------|
| Sve fotke na jednog `Guest` | Krivi dokumenti, krivi eVisitor |
| Pretpostaviti redoslijed (1)(2)(3) bez MRZ | Zamijenjene stražnje strane |
| `IdDocument.objects.create(tenant=...)` | `TypeError` — model nema `tenant` |
| Avatar konverzija unutar `docker exec` | `PermissionError` na `/root/.cursor/...` |
| Adresa `ulica, grad` | eVisitor HTTP 400 na `CityOfResidence` |
| Zanemariti drugog odraslog na rezervaciji | Samo jedan gost prijavljen u eVisitor |

---

## 9. Pronalaženje rezervacije u bazi

```python
from apps.reservations.models import Guest, Reservation
from datetime import date, timedelta

today = date(2026, 6, 1)
for r in Reservation.objects.filter(
    check_in__gte=today - timedelta(days=1),
    check_in__lte=today + timedelta(days=2),
).exclude(status="canceled"):
    for g in r.guests.all():
        print(r.id, r.status, r.check_in, g.id, g.name, g.is_primary, g.document_number, g.evisitor_status)
```

Traži: `checked_in` + prazan `document_number` / `evisitor_status`, ili prezime s OCR-a (`Kreft`, `Fischer`, `Nolleweit`).

---

## 10. Kronologija implementacija (agent)

| Datum | Zadatak | Rezultat |
|-------|---------|----------|
| 31.05.2026 | Nolleweit #1120 / #115 | OCR, medij, check-in, eVisitor sent |
| 01.06.2026 | Kreft + Szczypior #810 | 2 gosta, putovnica + osobna, eVisitor ×2 |
| 01.06.2026 | Fischer + Otto #810 | MRZ uparivanje, 2 gosta, eVisitor ×2 |
| 01.06.2026 | Avatar #2213 Szczypior | Zamjena `010626_2213_idf.jpg` iz chata |

---

## 11. Reference u kodu

| Što | Putanja |
|-----|---------|
| Modeli | `backend/apps/reservations/models.py` (`Guest`, `IdDocument`) |
| eVisitor servis | `backend/apps/integrations/evisitor/service.py` |
| Mapper / adresa | `backend/apps/integrations/evisitor/mapper.py` |
| Face URL (recepcija) | `backend/apps/reservations/face_photo.py` |

**Nema potrebe za promjenom koda** za rutinski ručni OCR — samo operativni podaci + medij.
