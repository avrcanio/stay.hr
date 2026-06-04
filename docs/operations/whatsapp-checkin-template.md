# WhatsApp pred-check-in — predložak

Operativni predložak za traženje dokumenata i slanje detalja dolaska **prije** check-ina. Copy-paste u WhatsApp Business; zatim u zasebnoj poruci priložiti sliku ulaza.

**Slika ulaza:** `.imports/20260527_140049.jpg` (znak „Restaurant Uzorita”, broj 58, kapija s lozom)

**Povezano:** [ai-runbook-ocr-checkin-evisitor-2026-06.md](./ai-runbook-ocr-checkin-evisitor-2026-06.md), [id-document-import.md](../development/id-document-import.md)

---

## Metapodaci (zaglavlje datoteke)

```
KANAL: WhatsApp Business
Booking: {BOOKING_KOD}
Tel.: {TELEFON}
Jezik: {JEZIK}
Prilog: slika ulaza → .imports/20260527_140049.jpg
```

---

## Placeholderi

| Placeholder | Primjer |
|-------------|---------|
| `{IME}` / `{NAME}` | Wolfgang / Florin |
| `{BOOKING_KOD}` | 5036489024 |
| `{SOBA}` | Deluxe King Room R1 + R2 |
| `{CHECK_IN}` | 4. 6. 2026. |
| `{CHECK_OUT}` | 5. 6. 2026. |
| `{CHECK_IN_SAT}` | 15:00 |
| `{CIJENA}` | 180,15 |
| `{VALUTA}` | € |
| `{BROJ_ODRASLIH}` | 2 |
| `{PLAĆANJE}` | vidi tablicu ispod |

**Adresa (fiksno):** Ul. bana Josipa Jelačića 58, 22000 Šibenik  
**Maps:** https://maps.app.goo.gl/BN15CcMmmAapmjUs7

---

## Plaćanje — guest-friendly tekstovi

Logika usklađena s `resolve_payment_method()` u `backend/apps/billing/services/payment.py`. Za gosta **ne** koristiti fiskalni tekst „TRANSAKCIJSKI RAČUN”.

### Booking.com (Payments by Booking.com)

| Jezik | Tekst |
|-------|-------|
| **HR** | Ukupna cijena: {CIJENA} € — plaćeno u cijelosti putem Booking.com (Payments by Booking.com). Boravak ne plaćate na check-inu. |
| **EN** | Total price: €{CIJENA} — paid in full via Booking.com (Payments by Booking.com). No payment due for your stay at check-in. |
| **DE** | Gesamtpreis: {CIJENA} € — vollständig über Booking.com (Payments by Booking.com) bezahlt. Keine Zahlung für den Aufenthalt beim Check-in. |
| **RO** | Preț total: {CIJENA} € — plătit integral prin Booking.com (Payments by Booking.com). Nu este necesară plata cazării la check-in. |

### Gotovina

| Jezik | Tekst |
|-------|-------|
| **HR** | Ukupna cijena: {CIJENA} € — plaćanje gotovinom na check-inu. |
| **EN** | Total price: €{CIJENA} — payment in cash at check-in. |
| **DE** | Gesamtpreis: {CIJENA} € — Zahlung bar beim Check-in. |
| **RO** | Preț total: {CIJENA} € — plata cash la check-in. |

### Kartica

| Jezik | Tekst |
|-------|-------|
| **HR** | Ukupna cijena: {CIJENA} € — plaćanje karticom na check-inu. |
| **EN** | Total price: €{CIJENA} — payment by card at check-in. |
| **DE** | Gesamtpreis: {CIJENA} € — Zahlung mit Karte beim Check-in. |
| **RO** | Preț total: {CIJENA} € — plata cu cardul la check-in. |

### Transakcijski račun (izvan Booking.com)

| Jezik | Tekst |
|-------|-------|
| **HR** | Ukupna cijena: {CIJENA} € — plaćanje transakcijskim računom (prema dogovoru). |
| **EN** | Total price: €{CIJENA} — payment by bank transfer (as agreed). |
| **DE** | Gesamtpreis: {CIJENA} € — Zahlung per Banküberweisung (wie vereinbart). |
| **RO** | Preț total: {CIJENA} € — plată prin transfer bancar (conform acordului). |

---

## Check-in sat

Standard propertyja Uzorita: **od 15:00** (`Property.check_in_time`, default 15:00).

| Jezik | Tekst |
|-------|-------|
| **HR** | Check-in: {CHECK_IN} od {CHECK_IN_SAT} |
| **EN** | Check-in: {CHECK_IN} from {CHECK_IN_SAT} |
| **DE** | Check-in: {CHECK_IN} ab {CHECK_IN_SAT} Uhr |
| **RO** | Check-in: {CHECK_IN}, de la ora {CHECK_IN_SAT} |

---

## Ulaz (opis + prilog)

| Jezik | Tekst |
|-------|-------|
| **HR** | Ulaz: potražite natpis „Restaurant Uzorita” i broj **58** na bijelom zidu — kapija s vinovom lozom odmah desno od znaka. (Fotografiju ulaza šaljemo u sljedećoj poruci.) |
| **EN** | Entrance: look for the “Restaurant Uzorita” sign and house number **58** on the white wall — the gate with vines is just to the right of the sign. (We’ll send a photo of the entrance in the next message.) |
| **DE** | Eingang: Schild „Restaurant Uzorita” und Hausnummer **58** an der weißen Mauer — das Tor mit Weinreben rechts neben dem Schild. (Ein Foto des Eingangs folgt in der nächsten Nachricht.) |
| **RO** | Intrare: căutați panoul „Restaurant Uzorita” și numărul **58** pe peretele alb — poarta cu viță de vie imediat la dreapta panoului. (Trimitem fotografia intrării în mesajul următor.) |

---

## Dokumenti (pred-check-in)

| Jezik | Tekst |
|-------|-------|
| **HR** | Molimo prije dolaska pošaljite nam ovdje na WhatsApp fotografije dokumenata za svakog odraslog gosta ({BROJ_ODRASLIH}): putovnica (stranica s podacima) ili osobna iskaznica (prednja + stražnja strana). Bez bljeskalice, cijeli dokument u kadru. Podatke koristimo isključivo za zakonsku prijavu boravka (eVisitor). |
| **EN** | Please send us photos of ID documents here on WhatsApp before arrival — one set per adult guest ({BROJ_ODRASLIH}): passport (biodata page) or national ID card (front + back). No flash, full document in frame. We use this data only for mandatory guest registration (eVisitor). |
| **DE** | Bitte senden Sie uns vor der Anreise Fotos der Ausweisdokumente hier per WhatsApp — pro erwachsenem Gast ({BROJ_ODRASLIH}): Reisepass (Datenseite) oder Personalausweis (Vorder- und Rückseite). Ohne Blitz, ganzes Dokument im Bild. Die Daten verwenden wir ausschließlich für die gesetzliche Meldepflicht (eVisitor). |
| **RO** | Vă rugăm să ne trimiteți pe WhatsApp, înainte de sosire, fotografii ale actelor de identitate — câte un set pentru fiecare adult ({BROJ_ODRASLIH}): pașaport (pagina cu date) sau carte de identitate (față + verso). Fără bliț, documentul complet în cadru. Datele sunt folosite exclusiv pentru înregistrarea legală a șederii (eVisitor). |

---

## Footer (obavezno)

```
Managed by stay.hr — https://stay.hr/
```

---

## Predložak tijela poruke (HR)

```
Bok {IME}!

Hvala na rezervaciji u Luxury Room Uzorita B&B.

Vaša rezervacija
• Broj: {BOOKING_KOD}
• Objekt: Luxury Room Uzorita B&B
• Soba: {SOBA}
• Datumi: {CHECK_IN} – {CHECK_OUT}
• {PLAĆANJE_HR}

{CHECK_IN_HR}

Adresa
Ul. bana Josipa Jelačića 58, 22000 Šibenik
https://maps.app.goo.gl/BN15CcMmmAapmjUs7

{ULAZ_HR}

{DOKUMENTI_HR}

Javite nam okvirno vrijeme dolaska kad pošaljete dokumente.

Lijep pozdrav,
Toni
Luxury Room Uzorita B&B
+385 99 838 8513

Managed by stay.hr — https://stay.hr/
```

---

## Primjeri za danas (4. 6. 2026.)

| Datoteka | Gost | Jezik |
|----------|------|-------|
| [whatsapp-5036489024-wolfgang-gross-de.txt](./whatsapp-5036489024-wolfgang-gross-de.txt) | Wolfgang Gross | DE |
| [whatsapp-6925385738-florin-stanciu-ro.txt](./whatsapp-6925385738-florin-stanciu-ro.txt) | Florin Stanciu | RO |

---

## Redoslijed slanja

1. Copy-paste tekst poruke
2. Odmah zatim slika ulaza (`.imports/20260527_140049.jpg`)
3. Nakon primitka dokumenata → OCR runbook → check-in u Hospiri
