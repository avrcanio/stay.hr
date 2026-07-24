"""Uzorita Property.guest_info seed payload."""

from __future__ import annotations

from apps.communications.guest_compose_defaults import (
    DEFAULT_ENTRANCE_IMAGE,
    DEFAULT_TEXTS,
    MAPS_LINK,
)
from apps.properties.uzorita_guide_i18n_extra import (
    apply_extra_breakfast_fact,
    apply_extra_guide_translations,
)

# Physical key tag numbers (ormarić) — not the same as unit.code (R1/R2/R3).
UZORITA_UNIT_KEY_LABELS: dict[str, str] = {
    "R1": "1",
    "R2": "2",
    "R3": "3",
    "R6": "6",
}

UZORITA_KEY_HANDOVER_GUIDE: dict = {
    "sections": {
        "intro": {
            "hr": (
                "Bok {first_name},\n\n"
                "hvala na rezervaciji u Uzorita B&B (soba {room_code}, check-in od {check_in_time}).\n\n"
                "Evo upute kako pronaći ključ i ući u sobu:"
            ),
            "en": (
                "Hi {first_name},\n\n"
                "thank you for your booking at Uzorita B&B (room {room_code}, check-in from {check_in_time}).\n\n"
                "Here is how to find your key and enter your room:"
            ),
            "de": (
                "Guten Tag {first_name},\n\n"
                "vielen Dank für Ihre Buchung bei Uzorita B&B (Zimmer {room_code}, Check-in ab {check_in_time} Uhr).\n\n"
                "So finden Sie den Schlüssel und betreten Ihr Zimmer:"
            ),
        },
        "entrance": {
            "hr": (
                "DOLAZAK I ADRESA\n"
                "{address}\n"
                "Google Maps: {maps_link}\n\n"
                "PRONAĐITE ULAZ\n"
                "Potražite natpis „Restaurant Uzorita“ / „Uzorita Rooms“ i kućni broj 58 na bijelom zidu. "
                "Desno od natpisa je crna kapija s vinovom lozom. S lijeve strane kapije vidi se plava pločica s brojem 58.\n\n"
                "KROZ KAPIJU\n"
                "Otvorite kapiju i idite ravno popločanim putem. Proći ćete uskim prolazom s vinovom lozom "
                "između zidova od prirodnog kamena i doći u unutarnje dvorište restorana."
            ),
            "en": (
                "ARRIVAL & ADDRESS\n"
                "{address}\n"
                "Google Maps: {maps_link}\n\n"
                "FIND THE ENTRANCE\n"
                'Look for the "Restaurant Uzorita" / "Uzorita Rooms" sign and house number 58 on the white wall. '
                "To the right of the sign is a black gate with vines above it. "
                "On the left side of the gate you will see a blue plaque with the number 58.\n\n"
                "THROUGH THE GATE\n"
                "Open the gate and walk straight along the paved path. "
                "You will pass a narrow passage covered with vines between natural stone walls "
                "and reach the restaurant courtyard."
            ),
            "de": (
                "ANKUNFT & ADRESSE\n"
                "{address}\n"
                "Google Maps: {maps_link}\n\n"
                "EINGANG FINDEN\n"
                "Suchen Sie das Schild „Restaurant Uzorita“ / „Uzorita Rooms“ und die Hausnummer 58 an der weißen Mauer. "
                "Rechts neben dem Schild ist ein schwarzes Tor mit Weinreben darüber. "
                "An der linken Torseite sehen Sie eine blaue Tafel mit der Nummer 58.\n\n"
                "DURCH DAS TOR\n"
                "Öffnen Sie das Tor und gehen Sie den gepflasterten Weg geradeaus. "
                "Sie passieren einen schmalen, von Weinreben überwachsenen Durchgang mit Natursteinmauern "
                "und gelangen in den Innenhof des Restaurants."
            ),
        },
        "cabinet": {
            "hr": (
                "KLJUČEVI U ORMARIĆU\n"
                "U dvorištu, uz kameni zid, nalazi se mala drvena vitrina sa staklenim frontom "
                "i jelovnikom restorana Uzorita. Otvorite vrata vitrine — unutra visi ključevi soba na privjesnicima."
            ),
            "en": (
                "KEYS IN THE CABINET\n"
                "In the courtyard, against the stone wall, you will find a small wooden display case "
                "with a glass front and the Uzorita restaurant menu. "
                "Open the case — room keys hang inside on key rings."
            ),
            "de": (
                "SCHLÜSSEL IM ORMARIĆ (SCHLÜSSELKASTEN)\n"
                "Im Innenhof finden Sie an der Steinmauer einen kleinen Holzschaukasten mit dem "
                "Speisekarten-Jelovnik von Uzorita (Glasfront). "
                "Öffnen Sie die Tür des Kastens — darin hängen die Zimmerschlüssel an Schlüsselanhängern."
            ),
        },
        "key": {
            "hr": (
                "VAŠ KLJUČ — BROJ {key_label}\n"
                "Uzmite ključ s privjesnicom označenim brojem {key_label}. "
                "To je ključ za sobu {room_code} (Luxury Room Uzorita)."
            ),
            "en": (
                "YOUR KEY — NUMBER {key_label}\n"
                "Take the key with the tag numbered {key_label}. "
                "This is your key for room {room_code} (Luxury Room Uzorita)."
            ),
            "de": (
                "IHR SCHLÜSSEL — NUMMER {key_label}\n"
                "Nehmen Sie den Schlüssel mit dem Anhänger mit der Nummer {key_label}. "
                "Das ist Ihr Schlüssel für Zimmer {room_code} (Luxury Room Uzorita)."
            ),
        },
        "stairs": {
            "hr": (
                "DO SOBE\n"
                "Od tamo idite do kamenih stepenica u dvorištu (desno od kamenog zida). "
                "Stepenice vode gore do gostinskih soba. Vaša soba je {room_code}."
            ),
            "en": (
                "TO YOUR ROOM\n"
                "From there, go to the stone stairs in the courtyard (to the right of the stone wall). "
                "The stairs lead up to the guest rooms. Your room is {room_code}."
            ),
            "de": (
                "ZUM ZIMMER\n"
                "Gehen Sie von dort zu den Steintreppe im Innenhof (rechts neben der Steinmauer). "
                "Die Treppe führt nach oben zu den Gästezimmern. Ihr Zimmer ist {room_code}."
            ),
        },
        "breakfast": {
            "hr": (
                "DORUČAK\n"
                "Doručak u Restoranu Uzorita ({breakfast_hours}) uključen je u cijenu."
            ),
            "en": (
                "BREAKFAST\n"
                "Breakfast at Restaurant Uzorita ({breakfast_hours}) is included in your rate."
            ),
            "de": (
                "FRÜHSTÜCK\n"
                "Frühstück im Restaurant Uzorita ({breakfast_hours}) ist im Preis enthalten."
            ),
        },
        "parking": {
            "hr": (
                "PARKIRANJE\n"
                "Parkiranje u cijeloj zoni je besplatno. Možete parkirati ispred objekta ili u blizini."
            ),
            "en": (
                "PARKING\n"
                "Parking is free throughout the zone. You can park in front of the property or nearby."
            ),
            "de": (
                "PARKEN\n"
                "Parken ist in der gesamten Zone kostenlos. "
                "Sie können direkt vor dem Haus oder in der Nähe parken."
            ),
        },
        "documents": {
            "hr": (
                "CHECK-IN I DOKUMENTI\n"
                "Check-in je samostalan od {check_in_time}. "
                "Molimo pripremite identifikacijske dokumente svih odraslih gostiju za zakonsku prijavu (eVisitor). "
                "Ako nam želite unaprijed poslati fotografije dokumenata, odgovorite na ovu poruku."
            ),
            "en": (
                "CHECK-IN & DOCUMENTS\n"
                "Check-in is self-service from {check_in_time}. "
                "Please have ID documents ready for all adult guests for mandatory registration (eVisitor). "
                "If you would like to send us photos of your documents in advance, simply reply to this message."
            ),
            "de": (
                "CHECK-IN & DOKUMENTE\n"
                "Der Check-in erfolgt selbstständig ab {check_in_time} Uhr. "
                "Bitte halten Sie für die gesetzliche Meldepflicht (eVisitor) Ausweisdokumente "
                "für alle erwachsenen Gäste bereit. "
                "Falls Sie uns vorab Fotos Ihrer Ausweise schicken möchten, antworten Sie einfach auf diese Nachricht."
            ),
        },
        "checkout": {
            "hr": (
                "CHECK-OUT (do 11:00)\n"
                "Molimo ostavite ključ u vratima sobe prije odlaska."
            ),
            "en": (
                "CHECK-OUT (by 11:00)\n"
                "Please leave the key in your room door before departure."
            ),
            "de": (
                "CHECK-OUT (bis 11:00 Uhr)\n"
                "Bitte legen Sie den Schlüssel vor Ihrer Abreise in der Zimmertür zurück."
            ),
        },
        "contact": {
            "hr": (
                "UPITI ILI KASNI DOLAZAK\n"
                "Pišite nam ovdje ili nazovite: {contact_phone}."
            ),
            "en": (
                "QUESTIONS OR LATE ARRIVAL\n"
                "Message us here or call: {contact_phone}."
            ),
            "de": (
                "BEI FRAGEN ODER SPÄTER ANKUNFT\n"
                "Schreiben Sie uns hier oder rufen Sie uns an: {contact_phone}."
            ),
        },
    },
    "order": [
        "intro",
        "entrance",
        "cabinet",
        "key",
        "stairs",
        "breakfast",
        "parking",
        "documents",
        "checkout",
        "contact",
    ],
    "steps": [
        {
            "section": "entrance",
            "image": "assets/guest-portal/uzorita/steps/01_gate.jpg",
            "caption": {
                "hr": "Plava pločica s brojem 58 lijevo od crne kapije.",
                "en": "Blue plaque with number 58 on the left side of the black gate.",
                "de": "Blaue Tafel mit der Nummer 58 an der linken Torseite.",
            },
        },
        {
            "section": "entrance",
            "image": "assets/guest-portal/uzorita/steps/02_entrance.jpg",
            "caption": {
                "hr": 'Natpis „Restaurant Uzorita“ / „Uzorita Rooms“ i kućni broj 58.',
                "en": '"Restaurant Uzorita" / "Uzorita Rooms" sign and house number 58.',
                "de": 'Schild „Restaurant Uzorita“ / „Uzorita Rooms“ und Hausnummer 58.',
            },
        },
        {
            "section": "entrance",
            "image": "assets/guest-portal/uzorita/steps/03_passage.jpg",
            "caption": {
                "hr": "Prođite kroz kapiju i uskim prolazom do unutarnjeg dvorišta.",
                "en": "Walk through the gate and the narrow passage to the inner courtyard.",
                "de": "Gehen Sie durch das Tor und den schmalen Durchgang in den Innenhof.",
            },
        },
        {
            "section": "cabinet",
            "image": "assets/guest-portal/uzorita/steps/04_cabinet.jpg",
            "caption": {
                "hr": "Drvena vitrina uz kameni zid — otvorite vrata za ključeve.",
                "en": "Wooden display case against the stone wall — open the door for the keys.",
                "de": "Holzschaukasten an der Steinmauer — öffnen Sie die Tür für die Schlüssel.",
            },
        },
        {
            "section": "cabinet",
            "image": "assets/guest-portal/uzorita/steps/05_keys.jpg",
            "caption": {
                "hr": "Unutra visi ključevi soba na privjesnicima.",
                "en": "Room keys hang inside on key rings.",
                "de": "Zimmerschlüssel hängen darin an Schlüsselanhängern.",
            },
        },
        {
            "section": "key",
            "image": "assets/guest-portal/uzorita/steps/06_key_tag.jpg",
            "caption": {
                "hr": "Uzmite ključ s privjesnicom broj {key_label} (soba {room_code}).",
                "en": "Take the key with tag number {key_label} (room {room_code}).",
                "de": "Nehmen Sie den Schlüssel mit Anhänger Nummer {key_label} (Zimmer {room_code}).",
            },
        },
        {
            "section": "stairs",
            "image": "assets/guest-portal/uzorita/steps/07_stairs_view.jpg",
            "caption": {
                "hr": "Kamenite stepenice u dvorištu vode gore do gostinskih soba.",
                "en": "Stone stairs in the courtyard lead up to the guest rooms.",
                "de": "Steintreppe im Innenhof führt nach oben zu den Gästezimmern.",
            },
        },
        {
            "section": "stairs",
            "image": "assets/guest-portal/uzorita/steps/08_stairs.jpg",
            "caption": {
                "hr": "Vaša soba je {room_code} — gore stepenicama.",
                "en": "Your room is {room_code} — up the stairs.",
                "de": "Ihr Zimmer ist {room_code} — die Treppe hinauf.",
            },
        },
    ],

}

UZORITA_AI_NOTES = (
    "Accommodation rooms are above Restaurant Uzorita — look for the ROOMS sign at the entrance. "
    "Check-in from 15:00. Free parking throughout the zone; you may park in front of the restaurant "
    "or nearby. Please let us know your approximate arrival time."
)

UZORITA_GUEST_INFO: dict = {
    "canonical_language": "en",
    "links": {
        "maps_url": MAPS_LINK,
    },
    "assets": {
        "entrance_image": DEFAULT_ENTRANCE_IMAGE,
    },
    "facts": {
        "ai_notes": UZORITA_AI_NOTES,
        "reception_hours": "08:00–22:00",
        "wifi": {
            "ssid": "Uzoritarooms",
            "password": "77777777",
        },
        "breakfast": {
            "hr": (
                "Doručak u Restoranu Uzorita (7:30–9:30) uključen je u cijenu."
            ),
            "en": (
                "Breakfast at Restaurant Uzorita (7:30–9:30) is included in the rate."
            ),
            "de": (
                "Frühstück im Restaurant Uzorita (7:30–9:30) ist im Preis inbegriffen."
            ),
            "es": (
                "El desayuno en el Restaurant Uzorita (7:30–9:30) está incluido en la tarifa."
            ),
            "fr": (
                "Le petit-déjeuner au Restaurant Uzorita (7:30–9:30) est inclus dans le tarif."
            ),
            "sk": (
                "Raňajky v reštaurácii Uzorita (7:30–9:30) sú zahrnuté v cene."
            ),
            "hours": "7:30–9:30",
        },
        "parking": {
            "has_private": True,
            "zone_label": "cijela zona (besplatno)",
            "price_per_day": "0",
            "currency": "EUR",
            "large_vehicles_allowed": True,
            "custom": {
                "hr": (
                    "Možete parkirati ispred restorana ako ima mjesta, "
                    "ili bilo gdje u neposrednoj blizini."
                ),
                "en": (
                    "You may park in front of the restaurant if there is space, "
                    "or anywhere nearby."
                ),
            },
        },
    },
    "texts": dict(DEFAULT_TEXTS),
    "guide": UZORITA_KEY_HANDOVER_GUIDE,
}

apply_extra_guide_translations(UZORITA_GUEST_INFO["guide"])
apply_extra_breakfast_fact(UZORITA_GUEST_INFO["facts"])
