# Product stranica — screenshotovi

Stranica `/product` na `stay.hr` prikazuje screenshotove iz `public/product/`. Ako datoteka postoji, placeholder se automatski zamjenjuje (provjera u [`lib/product-screenshots.ts`](../lib/product-screenshots.ts)).

**Status:** svih 12 slika je u repou i prikazuje se na stranici.

## Datoteke (12)

| Datoteka | Tip okvira | Sekcija | Sadržaj |
|----------|------------|---------|---------|
| `booking-search.png` | browser 16:10 | Stay Booking | Pretraga dostupnosti — sobe, datumi, status |
| `booking-checkout.png` | browser 16:10 | Stay Booking | Checkout — podaci bookera |
| `reception-timeline.png` | browser 16:10 | Recepcija web | Timeline — filteri, pretraga, statusi |
| `reception-calendar.png` | browser 16:10 | Recepcija web | Kalendar po sobama — cijene, channel |
| `reception-detail.png` | browser 16:10 | Recepcija web | Detalj rezervacije — financije, poruke |
| `hospira-timeline.png` | phone 9:19 | Hospira | Timeline — dolasci, odlasci, prijavljeni |
| `hospira-calendar-rooms.png` | phone 9:19 | Hospira | Kalendar po sobama — cijene, inicijali |
| `hospira-calendar-occupancy.png` | phone 9:19 | Hospira | Kalendar zauzetosti po mjesecima |
| `hospira-messages.png` | phone 9:19 | Hospira | Inbox poruka (Channex, WhatsApp) |
| `hospira-reviews.png` | phone 9:19 | Hospira | Recenzije s kanala |
| `hospira-statistics-monthly.png` | phone 9:19 | Hospira | Statistike — usporedba mjeseci |
| `hospira-statistics-annual.png` | phone 9:19 | Hospira | Godišnji pregled, gosti po državama |

## Pravila za zamjenu slika

- **Osobni podaci:** blur ili zamijenite imena gostiju, brojeve dokumenata, telefone, ID rezervacija prije produkcijskog deploya.
- **Imena objekata:** marketing tekst na stranici ne spominje klijente; screenshotovi po želji anonymizirati.
- **Web:** širina ~1280 px, light mode.
- **Hospira:** portrait, status bar vidljiv.
- **Format:** PNG ili WebP, preporuka max ~1600 px širine.

## Kako zamijeniti

1. Snimite novi screenshot s istim imenom datoteke.
2. Prepišite datoteku u `web/booking/public/product/`.
3. Redeploy booking weba — nema promjene koda.

## Mapiranje u kodu

ID-evi u `PRODUCT_SCREENSHOT_FILES` (`lib/product-screenshots.ts`) odgovaraju imenima datoteka iz tablice gore.

## Channel manager sekcija

Stranica `/product` uključuje sekciju **Upravljanje kanalima** — Stay.hr + Channex integracija.

- UI: [`app/_components/ProductChannelManagerSection.tsx`](../app/_components/ProductChannelManagerSection.tsx)
- Popis kanala: [`lib/channex-channels.ts`](../lib/channex-channels.ts) (519 kanala, deduplicirano po šifri)
- Regeneracija popisa iz Channex docs: `node tool/gen-channex-channels.mjs`
- Izvor: [Channex Channel Codes](https://docs.channex.io/api-v.1-documentation/channel-codes)
