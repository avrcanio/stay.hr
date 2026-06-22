"""Default guest message templates (fallback when Property.guest_info is empty)."""

from __future__ import annotations

MAPS_LINK = "https://maps.app.goo.gl/BN15CcMmmAapmjUs7"
DEFAULT_ADDRESS = "Ul. bana Josipa Jelačića 58, 22000 Šibenik"
DEFAULT_ENTRANCE_IMAGE = "assets/whatsapp/uzorita_entrance.jpg"

ENTRANCE_TEXTS = {
    "hr": (
        'Ulaz: potražite natpis „Restaurant Uzorita” i broj **58** na bijelom zidu — '
        "kapija s vinovom lozom odmah desno od znaka. "
        "(Fotografiju ulaza šaljemo u sljedećoj poruci.)"
    ),
    "en": (
        'Entrance: look for the "Restaurant Uzorita" sign and house number **58** on the white wall — '
        "the gate with vines is just to the right of the sign. "
        "(We'll send a photo of the entrance in the next message.)"
    ),
    "de": (
        "Eingang: Schild „Restaurant Uzorita” und Hausnummer **58** an der weißen Mauer — "
        "das Tor mit Weinreben rechts neben dem Schild. "
        "(Ein Foto des Eingangs folgt in der nächsten Nachricht.)"
    ),
    "es": (
        'Entrada: busque el cartel «Restaurant Uzorita» y el número **58** en la pared blanca — '
        "la puerta con hiedra está justo a la derecha del cartel. "
        "(Enviaremos una foto de la entrada en el siguiente mensaje.)"
    ),
    "fr": (
        "Entrée : repérez l’enseigne « Restaurant Uzorita » et le numéro **58** sur le mur blanc — "
        "le portail avec la vigne est juste à droite de l’enseigne. "
        "(Nous enverrons une photo de l’entrée dans le message suivant.)"
    ),
}

PARKING_TEXTS = {
    "hr": (
        "Parkiranje: u cijeloj zoni parkiranje je besplatno. "
        "Možete parkirati odmah ispred objekta; ako nema mjesta, slobodno bilo gdje u neposrednoj blizini."
    ),
    "en": (
        "Parking: parking is free throughout the zone. "
        "You can park right in front of the property; if there is no space, anywhere nearby is fine."
    ),
    "de": (
        "Parken: In der gesamten Zone ist das Parken kostenlos. "
        "Sie können direkt vor dem Haus parken; wenn kein Platz frei ist, finden Sie problemlos einen Parkplatz in unmittelbarer Nähe."
    ),
    "es": (
        "Aparcamiento: el aparcamiento es gratuito en toda la zona. "
        "Puede aparcar justo delante del alojamiento; si no hay sitio, en cualquier lugar cercano."
    ),
    "fr": (
        "Stationnement : le stationnement est gratuit dans toute la zone. "
        "Vous pouvez vous garer juste devant l’établissement ; s’il n’y a pas de place, n’importe où à proximité."
    ),
}

DOCUMENTS_TEXTS = {
    "hr": (
        "Check-in — dokumenti\n"
        "Molimo prije dolaska pošaljite nam ovdje na WhatsApp fotografije dokumenata "
        "za svakog odraslog gosta ({adults}): putovnica (stranica s podacima) ili "
        "osobna iskaznica (prednja + stražnja strana). Bez bljeskalice, cijeli dokument u kadru. "
        "Podatke koristimo isključivo za zakonsku prijavu boravka (eVisitor)."
    ),
    "en": (
        "Check-in — documents\n"
        "Please send us photos of ID documents here on WhatsApp before arrival — "
        "one set per adult guest ({adults}): passport (biodata page) or national ID card "
        "(front + back). No flash, full document in frame. "
        "We use this data only for mandatory guest registration (eVisitor)."
    ),
    "de": (
        "Check-in vorbereiten\n"
        "Bitte senden Sie uns vor der Anreise Fotos der Ausweisdokumente hier per WhatsApp — "
        "pro erwachsenem Gast ({adults}): Reisepass (Datenseite) oder Personalausweis "
        "(Vorder- und Rückseite). Ohne Blitz, ganzes Dokument im Bild. "
        "Die Daten verwenden wir ausschließlich für die gesetzliche Meldepflicht (eVisitor)."
    ),
    "es": (
        "Check-in — documentos\n"
        "Por favor, envíenos fotos de los documentos de identidad por WhatsApp antes de la llegada — "
        "un juego por cada huésped adulto ({adults}): pasaporte (página de datos) o DNI "
        "(anverso y reverso). Sin flash, documento completo en la imagen. "
        "Usamos estos datos únicamente para el registro legal de la estancia (eVisitor)."
    ),
    "fr": (
        "Check-in — documents\n"
        "Veuillez nous envoyer par WhatsApp, avant votre arrivée, des photos des pièces d’identité — "
        "un jeu par adulte ({adults}) : passeport (page d’identité) ou carte d’identité "
        "(recto et verso). Sans flash, document entier visible. "
        "Nous utilisons ces données uniquement pour l’enregistrement légal du séjour (eVisitor)."
    ),
}

DOCUMENTS_BATCH_CONFIRM = {
    "hr": "Primili smo fotografije. Jeste li poslali sve dokumente za sve odrasle goste?",
    "en": "We received your photos. Have you sent ID documents for all adult guests?",
    "de": "Wir haben Ihre Fotos erhalten. Haben Sie Ausweisdokumente für alle erwachsenen Gäste gesendet?",
    "es": "Hemos recibido sus fotos. ¿Ha enviado documentos de identidad de todos los huéspedes adultos?",
    "fr": "Nous avons reçu vos photos. Avez-vous envoyé les pièces d’identité de tous les adultes ?",
}

DOCUMENTS_BATCH_CONFIRM_YES = {
    "hr": "Da",
    "en": "Yes",
    "de": "Ja",
    "es": "Sí",
    "fr": "Oui",
}

DOCUMENTS_BATCH_CONFIRM_NO = {
    "hr": "Ne",
    "en": "No",
    "de": "Nein",
    "es": "No",
    "fr": "Non",
}

DOCUMENTS_BATCH_ADDITIONAL_PHOTO = {
    "hr": (
        "Primili smo dodatnu fotografiju. Kad pošaljete sve dokumente, "
        "odgovorite **Da** na pitanje ispod."
    ),
    "en": (
        "We received an additional photo. When you have sent all documents, "
        "please reply **Yes** to the question below."
    ),
    "de": (
        "Wir haben ein zusätzliches Foto erhalten. Wenn Sie alle Dokumente gesendet haben, "
        "antworten Sie bitte mit **Ja** auf die Frage unten."
    ),
    "es": (
        "Hemos recibido una foto adicional. Cuando haya enviado todos los documentos, "
        "responda **Sí** a la pregunta siguiente."
    ),
    "fr": (
        "Nous avons reçu une photo supplémentaire. Lorsque vous avez envoyé tous les documents, "
        "répondez **Oui** à la question ci-dessous."
    ),
}

DOCUMENTS_BATCH_COMPLETE_REPROMPT = {
    "hr": (
        "Sve potrebne strane dokumenata su primljene.\n\n"
        "Molimo potvrdite gumbom **Da** ako ste poslali sve dokumente za sve odrasle goste."
    ),
    "en": (
        "We have received all required document sides.\n\n"
        "Please confirm with **Yes** if you have sent ID documents for all adult guests."
    ),
    "de": (
        "Alle erforderlichen Ausweisseiten wurden empfangen.\n\n"
        "Bitte bestätigen Sie mit **Ja**, wenn Sie Ausweisdokumente für alle erwachsenen Gäste gesendet haben."
    ),
    "es": (
        "Hemos recibido todas las caras necesarias del documento.\n\n"
        "Confirme con **Sí** si ha enviado documentos de identidad de todos los huéspedes adultos."
    ),
    "fr": (
        "Toutes les faces requises des documents ont été reçues.\n\n"
        "Veuillez confirmer avec **Oui** si vous avez envoyé les pièces d’identité de tous les adultes."
    ),
}

OPERATOR_DOCUMENTS_CONFIRM = {
    "hr": (
        "Primili smo fotografije. Jeste li unijeli sve potrebne slike dokumenta "
        "(sve strane ID-a za sve goste)?"
    ),
    "en": (
        "We received your photos. Have you uploaded all required document photos "
        "(all ID sides for all guests)?"
    ),
    "de": (
        "Wir haben Ihre Fotos erhalten. Haben Sie alle erforderlichen Dokumentenfotos "
        "(alle Ausweisseiten für alle Gäste) hochgeladen?"
    ),
    "es": (
        "Hemos recibido sus fotos. ¿Ha subido todas las fotos de documentos necesarias "
        "(todas las caras del ID para todos los huéspedes)?"
    ),
    "fr": (
        "Nous avons reçu vos photos. Avez-vous envoyé toutes les photos de documents requises "
        "(toutes les faces d’identité pour tous les clients) ?"
    ),
}

CHECKIN_PARTIAL_DOCUMENTS = {
    "hr": (
        "Primili smo dokumente — hvala!\n\n"
        "Molimo pošaljite još fotografije dokumenata za preostale odrasle goste na rezervaciji."
    ),
    "en": (
        "We received your documents — thank you!\n\n"
        "Please send ID photos for the remaining adult guests on your reservation."
    ),
    "de": (
        "Wir haben Ihre Dokumente erhalten — vielen Dank!\n\n"
        "Bitte senden Sie noch Ausweisfotos für die übrigen erwachsenen Gäste Ihrer Buchung."
    ),
    "es": (
        "Hemos recibido sus documentos — ¡gracias!\n\n"
        "Por favor, envíe fotos de identidad de los demás huéspedes adultos de la reserva."
    ),
    "fr": (
        "Nous avons bien reçu vos documents — merci !\n\n"
        "Veuillez envoyer les photos d’identité des autres adultes de la réservation."
    ),
}

MISSING_ID_SIDES_INTRO = {
    "hr": "Primili smo dokumente — hvala!\n\nMolimo pošaljite još:",
    "en": "We received your documents — thank you!\n\nPlease send the following:",
    "de": "Wir haben Ihre Dokumente erhalten — vielen Dank!\n\nBitte senden Sie noch:",
    "es": "Hemos recibido sus documentos — ¡gracias!\n\nPor favor, envíe lo siguiente:",
    "fr": "Nous avons bien reçu vos documents — merci !\n\nVeuillez envoyer ce qui suit :",
}

MISSING_ID_SIDE_LINE = {
    "hr": "• {name} — nedostaje {side_label}",
    "en": "• {name} — missing {side_label}",
    "de": "• {name} — fehlend: {side_label}",
    "es": "• {name} — falta {side_label}",
    "fr": "• {name} — manquant : {side_label}",
}

MISSING_ID_SIDE_LABEL_NATIONAL_FRONT = {
    "hr": "prednja strana osobne iskaznice",
    "en": "front of the ID card",
    "de": "Vorderseite des Personalausweises",
    "es": "anverso del documento de identidad",
    "fr": "recto de la carte d’identité",
}

MISSING_ID_SIDE_LABEL_NATIONAL_BACK = {
    "hr": "stražnja strana osobne iskaznice",
    "en": "back of the ID card",
    "de": "Rückseite des Personalausweises",
    "es": "reverso del documento de identidad",
    "fr": "verso de la carte d’identité",
}

MISSING_ID_SIDE_LABEL_PASSPORT = {
    "hr": "stranica s podacima putovnice",
    "en": "passport biodata page",
    "de": "Passdatenseite",
    "es": "página de datos del pasaporte",
    "fr": "page d’identité du passeport",
}

MISSING_GUEST_DOCUMENT_LINE = {
    "hr": "• {name} — nedostaje dokument",
    "en": "• {name} — document missing",
    "de": "• {name} — Dokument fehlt",
    "es": "• {name} — falta el documento",
    "fr": "• {name} — document manquant",
}

UNMATCHED_PERSON_LINE = {
    "hr": "• {name} — nije mapirano na rezervaciju",
    "en": "• {name} — not matched to reservation",
    "de": "• {name} — nicht auf Reservierung zugeordnet",
    "es": "• {name} — no asignado a la reserva",
    "fr": "• {name} — non associé à la réservation",
}

UNREAD_PHOTOS_INTRO = {
    "hr": (
        "Primili smo {total} fotografija, ali {unread} nismo mogli pročitati kao osobnu iskaznicu. "
        "Molimo pošaljite jasnu prednju i stražnju stranu {missing_guest_hint}."
    ),
    "en": (
        "We received {total} photos, but could not read {unread} as an ID card. "
        "Please send a clear front and back of {missing_guest_hint}."
    ),
    "de": (
        "Wir haben {total} Fotos erhalten, konnten aber {unread} nicht als Personalausweis lesen. "
        "Bitte senden Sie die Vorder- und Rückseite von {missing_guest_hint}."
    ),
    "es": (
        "Recibimos {total} fotos, pero no pudimos leer {unread} como documento de identidad. "
        "Envíe el anverso y reverso de {missing_guest_hint}."
    ),
    "fr": (
        "Nous avons reçu {total} photos, mais n'avons pas pu lire {unread} comme carte d'identité. "
        "Veuillez envoyer le recto et le verso de {missing_guest_hint}."
    ),
}

MISSING_GUEST_HINT_OTHER_ADULT = {
    "hr": "drugog odraslog gosta",
    "en": "the other adult guest",
    "de": "des anderen erwachsenen Gastes",
    "es": "del otro huésped adulto",
    "fr": "l'autre invité adulte",
}

AUTOCHECKIN_WAIVED_BODY = {
    "hr": (
        "Pozdrav {first_name},\n\n"
        "Rok za automatski online check-in (Auto check-in) je istekao. Bez brige — molimo predočite "
        "osobne iskaznice na recepciji pri dolasku (putovnica ili osobna za svakog odraslog gosta).\n\n"
        "Neke informacije o boravku u {property_name}:\n\n"
        "Sobe su iznad restorana Uzorita. Na ulazu potražite natpis „Restaurant Uzorita” i broj 58 "
        "na bijelom zidu — kapija s vinovom lozom odmah desno od znaka. Check-in od 15:00.\n\n"
        "Parkiranje je besplatno u cijeloj zoni. Možete parkirati ispred objekta; ako nema mjesta, "
        "bilo gdje u blizini.\n\n"
        "Možete li nam javiti okvirno kada planirate stići?"
    ),
    "en": (
        "Hi {first_name},\n\n"
        "The online Auto check-in window has expired. No worries — please present your ID documents "
        "at reception when you arrive (passport or ID card for each adult guest).\n\n"
        "Some information about your stay at {property_name}:\n\n"
        "Rooms are above Restaurant Uzorita. At the entrance, look for the “Restaurant Uzorita” sign "
        "and house number 58 on the white wall — the gate with vines is just to the right of the sign. "
        "Check-in from 15:00.\n\n"
        "Parking is free throughout the zone. You can park in front of the property; if there is no "
        "space, anywhere nearby is fine.\n\n"
        "Could you let us know approximately when you plan to arrive?"
    ),
    "de": (
        "Guten Tag {first_name},\n\n"
        "Die Frist für den automatischen Online-Check-in (Auto check-in) ist abgelaufen. Kein Problem — "
        "bitte legen Sie Ihre Ausweisdokumente bei der Ankunft an der Rezeption vor "
        "(Reisepass oder Personalausweis für jeden erwachsenen Gast).\n\n"
        "Einige Informationen zu Ihrem Aufenthalt in {property_name}:\n\n"
        "Die Zimmer befinden sich über dem Restaurant Uzorita. Am Eingang suchen Sie das Schild "
        "„Restaurant Uzorita” und die Hausnummer 58 an der weißen Mauer — das Tor mit Weinreben "
        "ist rechts neben dem Schild. Check-in ab 15:00 Uhr.\n\n"
        "Parken ist in der gesamten Zone kostenlos. Sie können direkt vor dem Haus parken; "
        "wenn kein Platz frei ist, finden Sie einen Parkplatz in der Nähe.\n\n"
        "Könnten Sie uns mitteilen, wann Sie voraussichtlich ankommen?"
    ),
    "es": (
        "Hola {first_name},\n\n"
        "El plazo para el check-in automático en línea (Auto check-in) ha expirado. No hay problema — "
        "presente sus documentos de identidad en recepción a su llegada "
        "(pasaporte o documento de identidad de cada adulto).\n\n"
        "Algunas informaciones sobre su estancia en {property_name}:\n\n"
        "Las habitaciones están encima del Restaurant Uzorita. En la entrada, busque el cartel "
        "«Restaurant Uzorita» y el número 58 en la pared blanca — la puerta con hiedra está justo "
        "a la derecha del cartel. Check-in desde las 15:00.\n\n"
        "El aparcamiento es gratuito en toda la zona. Puede aparcar delante del alojamiento; "
        "si no hay sitio, en cualquier lugar cercano.\n\n"
        "¿Podría indicarnos aproximadamente cuándo planea llegar?"
    ),
    "fr": (
        "Bonjour {first_name},\n\n"
        "Le délai pour l’enregistrement automatique en ligne (Auto check-in) est expiré. Pas de souci — "
        "veuillez nous présenter vos pièces d’identité à l’accueil lors de votre arrivée "
        "(passeport ou carte d’identité pour chaque adulte).\n\n"
        "Quelques informations sur votre séjour à {property_name} :\n\n"
        "Les chambres sont situées au-dessus du Restaurant Uzorita. À l’entrée, repérez l’enseigne "
        "« Restaurant Uzorita » et le numéro 58 sur le mur blanc — le portail avec la vigne est juste "
        "à droite de l’enseigne. Enregistrement à partir de 15h00.\n\n"
        "Stationnement : gratuit dans toute la zone. Vous pouvez vous garer juste devant "
        "l’établissement ; s’il n’y a pas de place, n’importe où à proximité.\n\n"
        "Pourriez-vous nous indiquer à quelle heure vous prévoyez arriver, à peu près ?"
    ),
}

AUTOCHECKIN_PERIOD_ENDED = {
    "hr": (
        "Rok za automatski online check-in (Auto check-in) je završen. "
        "Molimo predočite dokumente na recepciji pri dolasku."
    ),
    "en": (
        "The online Auto check-in window has closed. "
        "Please present your ID documents at reception when you arrive."
    ),
    "de": (
        "Die Frist für den automatischen Online-Check-in (Auto check-in) ist abgelaufen. "
        "Bitte legen Sie Ihre Ausweisdokumente bei der Ankunft an der Rezeption vor."
    ),
    "es": (
        "El plazo del check-in automático en línea (Auto check-in) ha finalizado. "
        "Presente sus documentos en recepción a su llegada."
    ),
    "fr": (
        "Le délai pour l’enregistrement automatique en ligne (Auto check-in) est terminé. "
        "Veuillez présenter vos pièces d’identité à l’accueil lors de votre arrivée."
    ),
}

AUTOCHECKIN_EXPIRED_SHORT = {
    "hr": (
        "Rok za automatski online check-in je istekao. "
        "Check-in obavljamo na recepciji kad stignete — u sljedećim porukama šaljemo ulaz i parkiranje."
    ),
    "en": (
        "The online Auto check-in window has expired. "
        "We will check you in at reception when you arrive — we are sending entrance and parking details next."
    ),
    "de": (
        "Die Frist für den automatischen Online-Check-in ist abgelaufen. "
        "Den Check-in erledigen wir bei Ihrer Ankunft an der Rezeption — Eingang und Parken folgen in den nächsten Nachrichten."
    ),
    "es": (
        "El plazo del check-in automático en línea ha expirado. "
        "Le registraremos en recepción a su llegada — a continuación le enviamos la entrada y el aparcamiento."
    ),
    "fr": (
        "Le délai pour l’enregistrement automatique en ligne est expiré. "
        "Nous vous enregistrerons à l’accueil à votre arrivée — l’entrée et le stationnement suivent dans les prochains messages."
    ),
}

CHECKIN_AUTOMATION_FAILED = {
    "hr": (
        "Automatski check-in nije uspio — podatke ćemo upisati na recepciji kad stignete.\n\n"
        "Javite nam, molimo, okvirno vrijeme dolaska."
    ),
    "en": (
        "Automatic check-in did not succeed — we will register you at reception when you arrive.\n\n"
        "Please let us know your approximate arrival time."
    ),
    "de": (
        "Der automatische Check-in ist fehlgeschlagen — wir erfassen Ihre Daten bei der Ankunft an der Rezeption.\n\n"
        "Bitte teilen Sie uns Ihre ungefähre Ankunftszeit mit."
    ),
    "es": (
        "El check-in automático no ha funcionado — registraremos sus datos en recepción a su llegada.\n\n"
        "Por favor, indíquenos su hora aproximada de llegada."
    ),
    "fr": (
        "L’enregistrement automatique n’a pas abouti — nous saisirons vos données à l’accueil à votre arrivée.\n\n"
        "Merci de nous indiquer votre heure d’arrivée approximative."
    ),
}

CHECKIN_READY_BODY = {
    "hr": (
        "Hvala vam na poslanim dokumentima!\n\n"
        "Vaši podaci su spremljeni — kad stignete, check-in će proći brzo i nećete gubiti vrijeme.\n\n"
        "Javite nam, molimo, okvirno vrijeme dolaska."
    ),
    "en": (
        "Thank you for sending your documents!\n\n"
        "Your details are saved — when you arrive, check-in will be quick and you won’t lose time.\n\n"
        "Please let us know your approximate arrival time."
    ),
    "de": (
        "Vielen Dank für die Dokumente!\n\n"
        "Ihre Daten sind registriert — beim Check-in vor Ort geht es schnell, Sie verlieren keine Zeit.\n\n"
        "Bitte teilen Sie uns Ihre ungefähre Ankunftszeit mit."
    ),
    "es": (
        "¡Gracias por enviar los documentos!\n\n"
        "Sus datos están registrados — a su llegada, el check-in será rápido y no perderá tiempo.\n\n"
        "Por favor, indíquenos su hora aproximada de llegada."
    ),
    "fr": (
        "Merci pour l’envoi de vos documents !\n\n"
        "Vos données sont enregistrées — à votre arrivée, l’enregistrement sera rapide.\n\n"
        "Merci de nous indiquer votre heure d’arrivée approximative."
    ),
}

POST_CHECKIN_ARRIVAL_THANKS = {
    "hr": "Hvala na obavijesti o vremenu dolaska.",
    "en": "Thank you for letting us know your arrival time.",
    "de": "Vielen Dank für die Mitteilung Ihrer Ankunftszeit.",
    "es": "Gracias por informarnos de su hora de llegada.",
    "fr": "Merci pour l’information sur votre heure d’arrivée.",
}

POST_CHECKIN_PARKING = {
    "hr": (
        "Za parkiranje možete parkirati ispred našeg restorana ako ima mjesta, "
        "ili bilo gdje u blizini. Parkiranje je besplatno."
    ),
    "en": (
        "For parking, you can park in front of our restaurant if there is space available, "
        "or anywhere nearby. Parking is free of charge."
    ),
    "de": (
        "Fürs Parken können Sie vor unserem Restaurant parken, wenn ein Platz frei ist, "
        "oder anderswo in der Nähe. Parken ist kostenlos."
    ),
    "es": (
        "Para aparcar, puede aparcar delante de nuestro restaurante si hay espacio, "
        "o en cualquier sitio cercano. El aparcamiento es gratuito."
    ),
    "fr": (
        "Pour le stationnement, vous pouvez vous garer devant notre restaurant s’il reste de la place, "
        "ou n’importe où à proximité. Le stationnement est gratuit."
    ),
}

POST_CHECKIN_WELCOME_TODAY = {
    "hr": "Radujemo se vašem dolasku danas u {property_name}!",
    "en": "We look forward to welcoming you today at {property_name}!",
    "de": "Wir freuen uns darauf, Sie heute in {property_name} begrüßen zu dürfen!",
    "es": "¡Esperamos darle la bienvenida hoy en {property_name}!",
    "fr": "Nous avons hâte de vous accueillir aujourd’hui à {property_name} !",
}

POST_CHECKIN_WELCOME_EVENING = {
    "hr": "Radujemo se vašem dolasku večeras u {property_name}!",
    "en": "We look forward to welcoming you this evening at {property_name}!",
    "de": "Wir freuen uns darauf, Sie heute Abend in {property_name} begrüßen zu dürfen!",
    "es": "¡Esperamos darle la bienvenida esta noche en {property_name}!",
    "fr": "Nous avons hâte de vous accueillir ce soir à {property_name} !",
}

ENTRANCE_IMAGE_CAPTION = {
    "hr": "Ulaz u smještaj",
    "en": "Entrance to the accommodation",
    "de": "Eingang zur Unterkunft",
    "es": "Entrada al alojamiento",
    "fr": "Entrée de l’hébergement",
}

CHECKIN_COMPLETE_SUPPLEMENT_INTRO = {
    "hr": "Još nekoliko korisnih informacija za vaš boravak:",
    "en": "A few more details for your stay:",
    "de": "Noch einige wichtige Informationen zu Ihrem Aufenthalt:",
    "es": "Algunos datos más para su estancia:",
    "fr": "Quelques informations utiles pour votre séjour :",
}

CHECKIN_COMPLETE_ASK_ARRIVAL = {
    "hr": "Javite nam, molimo, kada možemo očekivati vaš dolazak.",
    "en": "Please let us know when we can expect your arrival.",
    "de": "Wann können wir mit Ihrer Ankunft rechnen? Bitte teilen Sie uns Ihre ungefähre Ankunftszeit mit.",
    "es": "¿Cuándo podemos esperar su llegada? Por favor, indíquenos su hora aproximada.",
    "fr": "Quand pouvons-nous attendre votre arrivée ? Merci de nous indiquer votre heure approximative.",
}

ARRIVAL_WINDOW_INFO = {
    "hr": (
        "Check-in je moguć od {check_in_time} do {check_in_latest_time}. "
        "Molimo javite nam okvirno vrijeme dolaska."
    ),
    "en": (
        "Check-in is available from {check_in_time} until {check_in_latest_time}. "
        "Please let us know your approximate arrival time."
    ),
    "de": (
        "Check-in ist von {check_in_time} bis {check_in_latest_time} möglich. "
        "Bitte teilen Sie uns Ihre ungefähre Ankunftszeit mit."
    ),
    "es": (
        "El check-in es posible de {check_in_time} a {check_in_latest_time}. "
        "Por favor, indíquenos su hora aproximada de llegada."
    ),
    "fr": (
        "L’enregistrement est possible de {check_in_time} à {check_in_latest_time}. "
        "Merci de nous indiquer votre heure d’arrivée approximative."
    ),
}

ARRIVAL_WINDOW_FROM_ONLY = {
    "hr": "Check-in je moguć od {check_in_time}. Molimo javite nam okvirno vrijeme dolaska.",
    "en": "Check-in is available from {check_in_time}. Please let us know your approximate arrival time.",
    "de": "Check-in ist ab {check_in_time} möglich. Bitte teilen Sie uns Ihre Ankunftszeit mit.",
    "es": "El check-in es posible a partir de las {check_in_time}. Indíquenos su hora de llegada.",
    "fr": "L’enregistrement est possible à partir de {check_in_time}. Indiquez votre heure d’arrivée.",
}

ARRIVAL_TIME_SAVED_THANKS = {
    "hr": "Hvala — zabilježili smo vaše vrijeme dolaska ({stated_time}).",
    "en": "Thank you — we have noted your arrival time ({stated_time}).",
    "de": "Vielen Dank — wir haben Ihre Ankunftszeit ({stated_time}) notiert.",
    "es": "Gracias — hemos registrado su hora de llegada ({stated_time}).",
    "fr": "Merci — nous avons noté votre heure d’arrivée ({stated_time}).",
}

ARRIVAL_LATE_CONTACT = {
    "hr": (
        "Hvala na obavijesti. Vaše vrijeme ({stated_time}) je nakon našeg redovnog prozora "
        "({check_in_time}–{check_in_latest_time}). Molimo javite se na {contact_phone} prije dolaska."
    ),
    "en": (
        "Thank you for letting us know. Your time ({stated_time}) is after our regular window "
        "({check_in_time}–{check_in_latest_time}). Please call {contact_phone} before you arrive."
    ),
    "de": (
        "Vielen Dank für die Info. Ihre Zeit ({stated_time}) liegt außerhalb unseres Fensters "
        "({check_in_time}–{check_in_latest_time}). Bitte rufen Sie {contact_phone} vor der Ankunft an."
    ),
    "es": (
        "Gracias por avisarnos. Su hora ({stated_time}) es después de nuestro horario "
        "({check_in_time}–{check_in_latest_time}). Llame al {contact_phone} antes de llegar."
    ),
    "fr": (
        "Merci pour l’information. Votre heure ({stated_time}) est après notre créneau "
        "({check_in_time}–{check_in_latest_time}). Appelez le {contact_phone} avant d’arriver."
    ),
}

ARRIVAL_LATE_NOT_ALLOWED = {
    "hr": (
        "Nažalost, ulaz nakon {check_in_latest_time} nije moguć. "
        "Molimo planirajte dolazak do {check_in_latest_time} (check-in od {check_in_time})."
    ),
    "en": (
        "Unfortunately, entry after {check_in_latest_time} is not possible. "
        "Please plan to arrive by {check_in_latest_time} (check-in from {check_in_time})."
    ),
    "de": (
        "Leider ist ein Zugang nach {check_in_latest_time} nicht möglich. "
        "Bitte planen Sie die Ankunft bis {check_in_latest_time} (Check-in ab {check_in_time})."
    ),
    "es": (
        "Lamentablemente, no es posible entrar después de las {check_in_latest_time}. "
        "Planifique llegar antes de las {check_in_latest_time} (check-in desde {check_in_time})."
    ),
    "fr": (
        "Malheureusement, l’accès après {check_in_latest_time} n’est pas possible. "
        "Merci de prévoir votre arrivée avant {check_in_latest_time} (enregistrement dès {check_in_time})."
    ),
}

OPERATOR_CHECKIN_COMPLETE_BODY = {
    "hr": (
        "Check-in je obavljen. Vaši podaci su spremljeni.\n\n"
        "Želimo vam ugodan boravak!"
    ),
    "en": (
        "Your check-in is complete. Your details have been saved.\n\n"
        "We wish you a pleasant stay!"
    ),
    "de": (
        "Ihr Check-in ist abgeschlossen. Ihre Daten wurden erfasst.\n\n"
        "Wir wünschen Ihnen einen angenehmen Aufenthalt!"
    ),
    "es": (
        "Su check-in está completado. Sus datos han sido registrados.\n\n"
        "¡Le deseamos una estancia agradable!"
    ),
    "fr": (
        "Votre enregistrement est terminé. Vos données ont été enregistrées.\n\n"
        "Nous vous souhaitons un agréable séjour !"
    ),
}

DOCS_AWAITING_ARRIVAL_BODY = {
    "hr": (
        "Hvala vam — dokumenti su spremljeni.\n\n"
        "Check-in ćemo obaviti kad stignete. "
        "U međuvremenu, evo informacija za ulaz i parkiranje."
    ),
    "en": (
        "Thank you — your documents are saved.\n\n"
        "We will complete check-in when you arrive. "
        "In the meantime, here is how to find the entrance and parking."
    ),
    "de": (
        "Vielen Dank — Ihre Dokumente sind gespeichert.\n\n"
        "Den Check-in erledigen wir bei Ihrer Ankunft. "
        "Hier finden Sie Eingang und Parken."
    ),
    "es": (
        "Gracias — sus documentos están guardados.\n\n"
        "Completaremos el check-in a su llegada. "
        "Mientras tanto, aquí tiene la entrada y el aparcamiento."
    ),
    "fr": (
        "Merci — vos documents sont enregistrés.\n\n"
        "Nous finaliserons l’enregistrement à votre arrivée. "
        "Voici l’entrée et le stationnement."
    ),
}

AUTOCHECKIN_WHATSAPP_INTRO_HEAD = {
    "hr": (
        "Danas možete obaviti brzi online check-in putem WhatsAppa.\n\n"
        "Kontaktirat ćemo vas s broja {display_phone}. Možete i sami započeti check-in."
    ),
    "en": (
        "You can complete a quick online check-in via WhatsApp today.\n\n"
        "We will contact you from {display_phone}. You can also start check-in yourself."
    ),
    "de": (
        "Heute können Sie den Online-Check-in per WhatsApp abschließen.\n\n"
        "Wir kontaktieren Sie von {display_phone}. Sie können den Check-in auch selbst starten."
    ),
    "es": (
        "Hoy puede completar el check-in online por WhatsApp.\n\n"
        "Le contactaremos desde {display_phone}. También puede iniciar el check-in."
    ),
    "fr": (
        "Aujourd’hui, vous pouvez effectuer l’enregistrement en ligne via WhatsApp.\n\n"
        "Nous vous contacterons depuis {display_phone}. "
        "Vous pouvez aussi démarrer l’enregistrement."
    ),
}

AUTOCHECKIN_WHATSAPP_INTRO_TAIL = {
    "hr": (
        "Ako check-in obavite preko linka, nećete dobiti zasebnu WhatsApp pozivnicu "
        "(utility poruku).\n\n"
        "Ako pišete s drugog telefona na WhatsAppu, pošaljite booking kod s potvrde.\n\n"
        "Rezervacija: {booking_code}"
    ),
    "en": (
        "If you check in via the link, you will not receive a separate WhatsApp invitation "
        "(utility message).\n\n"
        "If you message us from a different phone on WhatsApp, send the booking code from "
        "your confirmation.\n\n"
        "Booking: {booking_code}"
    ),
    "de": (
        "Wenn Sie den Check-in über den Link abschließen, erhalten Sie keine separate "
        "WhatsApp-Einladung (Utility-Nachricht).\n\n"
        "Wenn Sie von einer anderen Nummer auf WhatsApp schreiben, senden Sie die "
        "Buchungsnummer aus der Bestätigung.\n\n"
        "Buchung: {booking_code}"
    ),
    "es": (
        "Si completa el check-in mediante el enlace, no recibirá una invitación "
        "WhatsApp aparte (mensaje utility).\n\n"
        "Si escribe desde otro teléfono en WhatsApp, envíe el código de reserva de la "
        "confirmación.\n\n"
        "Reserva: {booking_code}"
    ),
    "fr": (
        "Si vous terminez via le lien, vous ne recevrez pas d’invitation WhatsApp "
        "séparée (message utility).\n\n"
        "Si vous écrivez depuis un autre numéro sur WhatsApp, envoyez le code de "
        "réservation de la confirmation.\n\n"
        "Réservation : {booking_code}"
    ),
}

AUTOCHECKIN_WA_ME_PREFILL = {
    "hr": "Auto check-in",
    "en": "Auto check-in",
    "de": "Autocheck-in",
    "es": "Auto check-in",
    "fr": "Auto check-in",
}

EVISITOR_REGISTERED = {
    "hr": (
        "Prijavljeni ste u eVisitor (zakonska prijava boravka).\n\n"
        "Želimo vam ugodan boravak!"
    ),
    "en": (
        "You are now registered in eVisitor (official guest registration).\n\n"
        "We wish you a pleasant stay!"
    ),
    "de": (
        "Sie sind jetzt in eVisitor registriert (gesetzliche Meldepflicht).\n\n"
        "Wir wünschen Ihnen einen angenehmen Aufenthalt!"
    ),
    "es": (
        "Ya está registrado en eVisitor (registro oficial de huéspedes).\n\n"
        "¡Le deseamos una estancia agradable!"
    ),
    "fr": (
        "Vous êtes maintenant enregistré dans eVisitor (enregistrement officiel).\n\n"
        "Nous vous souhaitons un agréable séjour !"
    ),
}

CHECKIN_LINE = {
    "hr": "Check-in: {check_in} od {check_in_time}",
    "en": "Check-in: {check_in} from {check_in_time}",
    "de": "Check-in: {check_in} ab {check_in_time} Uhr",
    "es": "Check-in: {check_in} a partir de las {check_in_time}",
    "fr": "Check-in : {check_in} à partir de {check_in_time}",
}

GREETING = {
    "hr": "Bok {name}!",
    "en": "Hi {name}!",
    "de": "Hallo {name}!",
    "es": "¡Hola {name}!",
    "fr": "Bonjour {name} !",
}

THANKS = {
    "hr": "Hvala na rezervaciji u {property_name}.",
    "en": "Thank you for your booking at {property_name}.",
    "de": "Vielen Dank für Ihre Buchung bei {property_name}.",
    "es": "Gracias por su reserva en {property_name}.",
    "fr": "Merci pour votre réservation chez {property_name}.",
}

RESERVATION_HEADER = {
    "hr": "Vaša rezervacija",
    "en": "Your reservation",
    "de": "Ihre Buchung",
    "es": "Su reserva",
    "fr": "Votre réservation",
}

ROOM_LABEL = {
    "hr": "Soba",
    "en": "Room",
    "de": "Zimmer",
    "es": "Habitación",
    "fr": "Chambre",
}

ADDRESS_LABEL = {
    "hr": "Adresa",
    "en": "Address",
    "de": "Adresse",
    "es": "Dirección",
    "fr": "Adresse",
}

SIGN_OFF = {
    "hr": "Lijep pozdrav,",
    "en": "Best regards,",
    "de": "Mit freundlichen Grüßen,",
    "es": "Un saludo cordial,",
    "fr": "Cordialement,",
}

DEFAULT_GUEST_NAME = {
    "hr": "Gost",
    "en": "Guest",
    "de": "Gast",
    "es": "Huésped",
    "fr": "Client",
}

DEFAULT_TEXTS: dict[str, dict[str, str]] = {
    "entrance": ENTRANCE_TEXTS,
    "parking": PARKING_TEXTS,
    "documents": DOCUMENTS_TEXTS,
    "documents_batch_confirm": DOCUMENTS_BATCH_CONFIRM,
    "documents_batch_confirm_yes": DOCUMENTS_BATCH_CONFIRM_YES,
    "documents_batch_confirm_no": DOCUMENTS_BATCH_CONFIRM_NO,
    "documents_batch_additional_photo": DOCUMENTS_BATCH_ADDITIONAL_PHOTO,
    "documents_batch_complete_reprompt": DOCUMENTS_BATCH_COMPLETE_REPROMPT,
    "operator_documents_confirm": OPERATOR_DOCUMENTS_CONFIRM,
    "checkin_partial_documents": CHECKIN_PARTIAL_DOCUMENTS,
    "missing_id_sides_intro": MISSING_ID_SIDES_INTRO,
    "missing_id_side_line": MISSING_ID_SIDE_LINE,
    "missing_id_side_label_national_front": MISSING_ID_SIDE_LABEL_NATIONAL_FRONT,
    "missing_id_side_label_national_back": MISSING_ID_SIDE_LABEL_NATIONAL_BACK,
    "missing_id_side_label_passport": MISSING_ID_SIDE_LABEL_PASSPORT,
    "missing_guest_document_line": MISSING_GUEST_DOCUMENT_LINE,
    "unmatched_person_line": UNMATCHED_PERSON_LINE,
    "unread_photos_intro": UNREAD_PHOTOS_INTRO,
    "missing_guest_hint_other_adult": MISSING_GUEST_HINT_OTHER_ADULT,
    "autocheckin_waived": AUTOCHECKIN_WAIVED_BODY,
    "autocheckin_period_ended": AUTOCHECKIN_PERIOD_ENDED,
    "autocheckin_expired_short": AUTOCHECKIN_EXPIRED_SHORT,
    "checkin_automation_failed": CHECKIN_AUTOMATION_FAILED,
    "checkin_ready": CHECKIN_READY_BODY,
    "post_checkin_arrival_thanks": POST_CHECKIN_ARRIVAL_THANKS,
    "parking_post_checkin": POST_CHECKIN_PARKING,
    "post_checkin_welcome_today": POST_CHECKIN_WELCOME_TODAY,
    "post_checkin_welcome_evening": POST_CHECKIN_WELCOME_EVENING,
    "entrance_image_caption": ENTRANCE_IMAGE_CAPTION,
    "operator_checkin_complete": OPERATOR_CHECKIN_COMPLETE_BODY,
    "docs_awaiting_arrival": DOCS_AWAITING_ARRIVAL_BODY,
    "checkin_complete_supplement_intro": CHECKIN_COMPLETE_SUPPLEMENT_INTRO,
    "checkin_complete_ask_arrival": CHECKIN_COMPLETE_ASK_ARRIVAL,
    "arrival_window_info": ARRIVAL_WINDOW_INFO,
    "arrival_window_from_only": ARRIVAL_WINDOW_FROM_ONLY,
    "arrival_time_saved_thanks": ARRIVAL_TIME_SAVED_THANKS,
    "arrival_late_contact": ARRIVAL_LATE_CONTACT,
    "arrival_late_not_allowed": ARRIVAL_LATE_NOT_ALLOWED,
    "autocheckin_whatsapp_intro_head": AUTOCHECKIN_WHATSAPP_INTRO_HEAD,
    "autocheckin_whatsapp_intro_tail": AUTOCHECKIN_WHATSAPP_INTRO_TAIL,
    "autocheckin_wa_me_prefill": AUTOCHECKIN_WA_ME_PREFILL,
    "evisitor_registered": EVISITOR_REGISTERED,
    "checkin_line": CHECKIN_LINE,
}
