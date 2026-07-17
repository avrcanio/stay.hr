# eVisitor — CountryOfResidence XXK (rezervacija #1019)

**Objekt:** Uzorita (tenant #2)  
**Datum događaja:** 17. srpnja 2026.  
**Rezervacija:** #1019 · booking `5270067653` · 16.–17.7.2026.

---

## Sažetak

Gost **#2907 Fisnik Hamzaj** uspješno prijavljen u eVisitor.  
Gost **#2908 Edona Hoxha** odbijen: eVisitor ne poznaje šifru **`XXK`** (Kosovo) za polje `CountryOfResidence`.

Uzrok: iz MRZ-a njemačke boravišne dozvole (`AR` + izdavatelj `D`) nationality token **`XXK`** upisan je u `document_country_iso3`, a mapper to šalje kao `CountryOfResidence`.

---

## Gosti

| Uloga | Guest ID | Ime | Dokument | eVisitor |
|-------|----------|-----|----------|----------|
| Primarni | #2907 | Fisnik Hamzaj | DE osobna `L2TL02L6F` · iso3 `DEU` | **sent** |
| Drugi | #2908 | Edona Hoxha | DE boravišna (`AR`) `YZ6T3CNPZ` · iso3 bilo `XXK` | **failed** → ispravljeno na `DEU` |

**MRZ #2908 (sažetak):**

```
ARD<YZ6T3CNPZ4<<<<<<<<<<<
8311106F3210248XXK<<<<<<2
HOXHA<<EDONA<<<<<<<<<<<<<<
```

- Tip dokumenta: `AR` (Aufenthaltstitel / boravišna dozvola)  
- Izdavatelj: `D` (Njemačka)  
- Nacionalnost u MRZ: `XXK` (Kosovo)  
- Adresa: Sinzig, Bachstrasse 50 A (Njemačka)

---

## Kronologija

| Vrijeme (17.7.2026. UTC) | Događaj |
|--------------------------|---------|
| 08:02:07 | #2907 `CheckInTourist` HTTP **200** → `sent` |
| 08:02:11 | #2908 `CheckInTourist` HTTP **400** → `failed` |
| 08:07:06 | Ponovni pokušaj #2908 — ConnectTimeout na eVisitor login (sekundarni problem) |
| ~08:14 | Ops ispravka: `document_country_iso3` `XXK` → `DEU` |

---

## Uzrok

Mapper u [`backend/apps/integrations/evisitor/mapper.py`](../../backend/apps/integrations/evisitor/mapper.py):

```python
country_of_residence = citizenship
if guest.document_country_iso3:
    country_of_residence = guest.document_country_iso3.strip().upper()[:3]
```

Za #2908 poslano:

| Polje | Vrijednost | Izvor |
|-------|------------|--------|
| `Citizenship` | `DEU` | `nationality=DE` → ISO3 |
| `CountryOfBirth` | `DEU` | isto |
| `CountryOfResidence` | **`XXK`** | `document_country_iso3` (krivo iz MRZ nationality) |

`EvisitorSubmission` #433:

```
[[[CountryOfResidence]]] 'XXK' [[[ne postoji u sustavu.]]]
```

eVisitor šifrarnik zemalja **ne sadrži** `XXK` (niti kao CountryOfResidence).

---

## Rješenje (ops)

```python
from apps.reservations.models import Guest

g = Guest.objects.get(id=2908)
g.document_country_iso3 = "DEU"
g.document_country_iso2 = "DE"
g.save(update_fields=["document_country_iso3", "document_country_iso2", "updated_at"])
```

Zatim u Hospiri: **Prijavi u eVisitor** (ili `submit_guest_checkin(guest, force_retry=True)`).

**Pravilo:** `document_country_iso3` = **zemlja izdavanja dokumenta / boravišta**, ne MRZ nationality token ako se razlikuje (npr. `XXK` na njemačkoj boravišnoj).

---

## Za riješiti u kodu (backlog)

1. **MRZ `AR` (boravišna):** izdavatelj (`D`→`DEU`) → `document_country_iso*`; nationality (`XXK`) → `nationality` (ISO2 `XK` ako podržano), **ne** u `document_country_iso3`.
2. **eVisitor Kosovo:** provjeriti valjanu šifru u eVisitor Country lookupu (ako postoji) za Citizenship kad je gost državljanin Kosova; ne slati `XXK` u `CountryOfResidence` bez mapiranja.
3. **Validacija prije submita:** lokalna lista poznatih eVisitor zemalja / warning kad `document_country_iso3` nije u šifrarniku (izbjeći generički 502).
4. **UI:** jasnija poruka iz `error_user_message` (`CountryOfResidence 'XXK' ne postoji…`) umjesto samo Bad Gateway.

---

## Povezani dokumenti i kod

| Što | Gdje |
|-----|------|
| Sličan incident (adresa) | [evisitor-adresa-res-190-2026-05-30.md](./evisitor-adresa-res-190-2026-05-30.md) |
| OCR / eVisitor runbook | [ai-runbook-ocr-checkin-evisitor-2026-06.md](./ai-runbook-ocr-checkin-evisitor-2026-06.md) |
| eVisitor mapper | `backend/apps/integrations/evisitor/mapper.py` |
| eVisitor lookups | `backend/apps/integrations/evisitor/lookups.py` |
| Logovi | `docker logs stay_django` — `evisitor-submit`, guest `2908`, `CheckInTourist` |
