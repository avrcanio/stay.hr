"""Manual guide translations for Uzorita key handover (fr, nl, es, lt, it, sk, uk)."""

from __future__ import annotations

EXTRA_GUIDE_LANGS = frozenset({"fr", "nl", "es", "lt", "it", "sk", "uk"})

EXTRA_GUIDE_SECTIONS: dict[str, dict[str, str]] = {
    "intro": {
        "fr": (
            "Bonjour {first_name},\n\n"
            "merci pour votre réservation à Uzorita B&B (chambre {room_code}, "
            "check-in à partir de {check_in_time}).\n\n"
            "Voici comment trouver votre clé et accéder à votre chambre :"
        ),
        "nl": (
            "Hallo {first_name},\n\n"
            "bedankt voor uw reservering bij Uzorita B&B (kamer {room_code}, "
            "inchecken vanaf {check_in_time}).\n\n"
            "Zo vindt u de sleutel en komt u in uw kamer :"
        ),
        "es": (
            "Hola {first_name},\n\n"
            "gracias por su reserva en Uzorita B&B (habitación {room_code}, "
            "check-in a partir de las {check_in_time}).\n\n"
            "Así puede encontrar la llave y entrar en su habitación:"
        ),
        "lt": (
            "Sveiki {first_name},\n\n"
            "dėkojame už rezervaciją Uzorita B&B (kambarys {room_code}, "
            "registracija nuo {check_in_time}).\n\n"
            "Štai kaip rasti raktą ir patekti į kambarį:"
        ),
        "it": (
            "Buongiorno {first_name},\n\n"
            "grazie per la prenotazione presso Uzorita B&B (camera {room_code}, "
            "check-in dalle {check_in_time}).\n\n"
            "Ecco come trovare la chiave e accedere alla camera:"
        ),
        "sk": (
            "Dobrý deň {first_name},\n\n"
            "ďakujeme za rezerváciu v Uzorita B&B (izba {room_code}, "
            "check-in od {check_in_time}).\n\n"
            "Tu je návod, ako nájsť kľúč a dostať sa do izby:"
        ),
        "uk": (
            "Вітаємо, {first_name}!\n\n"
            "дякуємо за бронювання в Uzorita B&B (номер {room_code}, "
            "заїзд з {check_in_time}).\n\n"
            "Ось як знайти ключ і потрапити до номера:"
        ),
    },
    "entrance": {
        "fr": (
            "ARRIVÉE & ADRESSE\n"
            "{address}\n"
            "Google Maps : {maps_link}\n\n"
            "TROUVER L'ENTRÉE\n"
            "Cherchez l'enseigne « Restaurant Uzorita » / « Uzorita Rooms » et le numéro 58 "
            "sur le mur blanc. À droite de l'enseigne se trouve un portail noir recouvert de vigne. "
            "À gauche du portail, vous verrez une plaque bleue avec le numéro 58.\n\n"
            "À TRAVERS LE PORTAIL\n"
            "Ouvrez le portail et avancez tout droit sur le chemin pavé. "
            "Vous passerez par un passage étroit couvert de vigne entre des murs en pierre naturelle "
            "jusqu'à la cour intérieure du restaurant."
        ),
        "nl": (
            "AANKOMST & ADRES\n"
            "{address}\n"
            "Google Maps: {maps_link}\n\n"
            "VIND DE INGANG\n"
            "Zoek het bord « Restaurant Uzorita » / « Uzorita Rooms » en huisnummer 58 op de witte muur. "
            "Rechts van het bord is een zwarte poort met wijnstokken erboven. "
            "Links van de poort ziet u een blauwe plaquette met nummer 58.\n\n"
            "DOOR DE POORT\n"
            "Open de poort en loop rechtdoor over het geplaveide pad. "
            "U passeert een smalle doorgang met wijnstokken tussen natuurstenen muren "
            "en komt in de binnenplaats van het restaurant."
        ),
        "es": (
            "LLEGADA Y DIRECCIÓN\n"
            "{address}\n"
            "Google Maps: {maps_link}\n\n"
            "ENCONTRAR LA ENTRADA\n"
            "Busque el cartel « Restaurant Uzorita » / « Uzorita Rooms » y el número 58 en la pared blanca. "
            "A la derecha del cartel hay un portón negro con enredaderas. "
            "A la izquierda del portón verá una placa azul con el número 58.\n\n"
            "A TRAVÉS DEL PORTÓN\n"
            "Abra el portón y siga recto por el camino pavimentado. "
            "Pasará por un pasaje estrecho cubierto de enredaderas entre muros de piedra natural "
            "hasta llegar al patio interior del restaurante."
        ),
        "lt": (
            "ATVYKIMAS IR ADRESAS\n"
            "{address}\n"
            "Google Maps: {maps_link}\n\n"
            "RASKITE ĮĮĖJIMĄ\n"
            "Ieškokite lentos « Restaurant Uzorita » / « Uzorita Rooms » ir numerio 58 ant baltos sienos. "
            "Dešinėje nuo lentos yra juodi vartai su vynmedžiais. "
            "Kairėje vartų pusėje pamatysite mėlyną lentelę su numeriu 58.\n\n"
            "PER VARTUS\n"
            "Atidarykite vartus ir eikite tiesiai grįstu taku. "
            "Pereisite per siaurą koridorių su vynmedžiais tarp natūralios akmenų sienų "
            "ir pateksite į restorano vidinį kiemą."
        ),
        "it": (
            "ARRIVO E INDIRIZZO\n"
            "{address}\n"
            "Google Maps: {maps_link}\n\n"
            "TROVARE L'INGRESSO\n"
            "Cercate l'insegna « Restaurant Uzorita » / « Uzorita Rooms » e il numero civico 58 "
            "sul muro bianco. A destra dell'insegna c'è un cancello nero con viti sopra. "
            "Sul lato sinistro del cancello vedrete una targa blu con il numero 58.\n\n"
            "ATTRAVERSO IL CANCELLO\n"
            "Aprite il cancello e procedete dritti lungo il sentiero pavimentato. "
            "Passerete attraverso un passaggio stretto coperto di viti tra muri in pietra naturale "
            "fino al cortile interno del ristorante."
        ),
        "sk": (
            "PRÍCHOD A ADRESA\n"
            "{address}\n"
            "Google Maps: {maps_link}\n\n"
            "NÁJDITE VSTUP\n"
            "Hľadajte tabuľu « Restaurant Uzorita » / « Uzorita Rooms » a číslo domu 58 na bielej stene. "
            "Vpravo od tabule je čierna brána s viničom. "
            "Na ľavej strane brány uvidíte modrú tabuľku s číslom 58.\n\n"
            "CEZ BRÁNU\n"
            "Otvorte bránu a choďte rovno po dláždenom chodníku. "
            "Prejdete úzkym priechodom porasteným viničom medzi prírodnými kamennými múrmi "
            "až do vnútorneho dvora reštaurácie."
        ),
        "uk": (
            "ПРИБУТТЯ ТА АДРЕСА\n"
            "{address}\n"
            "Google Maps: {maps_link}\n\n"
            "ЗНАЙДІТЬ ВХІД\n"
            "Шукайте табличку « Restaurant Uzorita » / « Uzorita Rooms » і номер будинку 58 "
            "на білій стіні. Праворуч від таблички — чорні ворота з виноградом. "
            "Ліворуч від воріт ви побачите синю табличку з номером 58.\n\n"
            "ЧЕРЕЗ ВОРОТА\n"
            "Відчиніть ворота й ідіть прямо вузькою брукованою стежкою. "
            "Ви пройдете вузьким проходом з виноградом між кам'яними стінами "
            "до внутрішнього дворика ресторану."
        ),
    },
    "cabinet": {
        "fr": (
            "CLÉS DANS LA VITRINE\n"
            "Dans la cour, contre le mur en pierre, vous trouverez une petite vitrine en bois "
            "avec une façade vitrée et le menu du restaurant Uzorita. "
            "Ouvrez la porte — les clés des chambres sont accrochées à l'intérieur."
        ),
        "nl": (
            "SLEUTELS IN DE KAST\n"
            "Op de binnenplaats, tegen de stenen muur, vindt u een kleine houten vitrine "
            "met glazen front en het menu van restaurant Uzorita. "
            "Open de deur — de kamersleutels hangen binnen aan sleutelhangers."
        ),
        "es": (
            "LLAVES EN LA VITRINA\n"
            "En el patio, junto al muro de piedra, hay una pequeña vitrina de madera "
            "con frontal de cristal y el menú del restaurante Uzorita. "
            "Abra la puerta — las llaves de las habitaciones cuelgan en el interior."
        ),
        "lt": (
            "RAKTAI SPINTELĖJE\n"
            "Kieme, prie akmeninės sienos, yra maža medinė vitrina su stiklo priekiniu stiklu "
            "ir restorano Uzorita meniu. "
            "Atidarykite duris — kambarių raktai kabo viduje ant raktų pakabukų."
        ),
        "it": (
            "CHIAVI NELLA VETRINA\n"
            "Nel cortile, contro il muro in pietra, troverete una piccola vetrina in legno "
            "con fronte in vetro e il menu del ristorante Uzorita. "
            "Aprite lo sportello — le chiavi delle camere sono appese all'interno."
        ),
        "sk": (
            "KĽÚČE V SKRINI\n"
            "Na dvore pri kamennom múre je malá drevená vitrína so skleneným predným panelom "
            "a menu reštaurácie Uzorita. "
            "Otvorte dvere — kľúče od izieb visia vo vnútri na kľúčeniciach."
        ),
        "uk": (
            "КЛЮЧІ В ШАФІ\n"
            "У дворі біля кам'яної стіни є невелика дерев'яна вітрина зі склом "
            "і меню ресторану Uzorita. "
            "Відчиніть двері — ключі від номерів висять всередині на брелоках."
        ),
    },
    "key": {
        "fr": (
            "VOTRE CLÉ — NUMÉRO {key_label}\n"
            "Prenez la clé avec le porte-clés numéroté {key_label}. "
            "C'est la clé de la chambre {room_code} (Luxury Room Uzorita)."
        ),
        "nl": (
            "UW SLEUTEL — NUMMER {key_label}\n"
            "Neem de sleutel met het label nummer {key_label}. "
            "Dit is uw sleutel voor kamer {room_code} (Luxury Room Uzorita)."
        ),
        "es": (
            "SU LLAVE — NÚMERO {key_label}\n"
            "Tome la llave con la etiqueta número {key_label}. "
            "Es la llave de la habitación {room_code} (Luxury Room Uzorita)."
        ),
        "lt": (
            "JŪSŲ RAKTAS — NUMERIS {key_label}\n"
            "Paimkite raktą su pakabuku numeriu {key_label}. "
            "Tai jūsų kambario {room_code} raktas (Luxury Room Uzorita)."
        ),
        "it": (
            "LA VOSTRA CHIAVE — NUMERO {key_label}\n"
            "Prendete la chiave con l'etichetta numero {key_label}. "
            "È la chiave della camera {room_code} (Luxury Room Uzorita)."
        ),
        "sk": (
            "VÁŠ KĽÚČ — ČÍSLO {key_label}\n"
            "Vezmite si kľúč s príveskom číslo {key_label}. "
            "Toto je kľúč od izby {room_code} (Luxury Room Uzorita)."
        ),
        "uk": (
            "ВАШ КЛЮЧ — НОМЕР {key_label}\n"
            "Візьміть ключ із брелоком номер {key_label}. "
            "Це ключ від номера {room_code} (Luxury Room Uzorita)."
        ),
    },
    "stairs": {
        "fr": (
            "VERS VOTRE CHAMBRE\n"
            "De là, allez aux escaliers en pierre dans la cour (à droite du mur en pierre). "
            "Les escaliers mènent aux chambres d'hôtes. Votre chambre est {room_code}."
        ),
        "nl": (
            "NAAR UW KAMER\n"
            "Ga vanaf daar naar de stenen trap op de binnenplaats (rechts van de stenen muur). "
            "De trap leidt naar de gastenkamers. Uw kamer is {room_code}."
        ),
        "es": (
            "HACIA SU HABITACIÓN\n"
            "Desde allí, diríjase a las escaleras de piedra en el patio (a la derecha del muro). "
            "Las escaleras suben a las habitaciones. Su habitación es {room_code}."
        ),
        "lt": (
            "Į KAMBARĮ\n"
            "Nuo ten eikite prie akmeninių laiptų kieme (dešinėje nuo akmeninės sienos). "
            "Laiptai veda į svečių kambarius. Jūsų kambarys — {room_code}."
        ),
        "it": (
            "VERSO LA CAMERA\n"
            "Da lì, raggiungete le scale in pietra nel cortile (a destra del muro in pietra). "
            "Le scale portano alle camere degli ospiti. La vostra camera è {room_code}."
        ),
        "sk": (
            "DO IZBY\n"
            "Odtiaľ choďte ku kamenným schodom na dvore (vpravo od kamenného múru). "
            "Schody vedú hore k hosťovským izbám. Vaša izba je {room_code}."
        ),
        "uk": (
            "ДО НОМЕРА\n"
            "Звідти пройдіть до кам'яних сходів у дворі (праворуч від кам'яної стіни). "
            "Сходи ведуть до гостьових номерів. Ваш номер — {room_code}."
        ),
    },
    "breakfast": {
        "fr": (
            "PETIT-DÉJEUNER\n"
            "Le petit-déjeuner au Restaurant Uzorita ({breakfast_hours}) est inclus dans le tarif."
        ),
        "nl": (
            "ONTBIJT\n"
            "Ontbijt in Restaurant Uzorita ({breakfast_hours}) is inbegrepen in de prijs."
        ),
        "es": (
            "DESAYUNO\n"
            "El desayuno en el Restaurant Uzorita ({breakfast_hours}) está incluido en la tarifa."
        ),
        "lt": (
            "PUSRYČIAI\n"
            "Pusryčiai restorane Uzorita ({breakfast_hours}) įskaičiuoti į kainą."
        ),
        "it": (
            "COLAZIONE\n"
            "La colazione al Restaurant Uzorita ({breakfast_hours}) è inclusa nel prezzo."
        ),
        "sk": (
            "RAANAJKY\n"
            "Raňajky v reštaurácii Uzorita ({breakfast_hours}) sú zahrnuté v cene."
        ),
        "uk": (
            "СНІДАНОК\n"
            "Сніданок у ресторані Uzorita ({breakfast_hours}) включено у вартість."
        ),
    },
    "parking": {
        "fr": (
            "PARKING\n"
            "Le stationnement est gratuit dans toute la zone. "
            "Vous pouvez vous garer devant l'établissement ou à proximité."
        ),
        "nl": (
            "PARKEREN\n"
            "Parkeren is gratis in de hele zone. "
            "U kunt voor het pand of in de buurt parkeren."
        ),
        "es": (
            "APARCAMIENTO\n"
            "El aparcamiento es gratuito en toda la zona. "
            "Puede aparcar delante del alojamiento o cerca."
        ),
        "lt": (
            "PARKAVIMAS\n"
            "Parkavimas visoje zonoje nemokamas. "
            "Galite statyti automobilį prie objekto arba netoliese."
        ),
        "it": (
            "PARCHEGGIO\n"
            "Il parcheggio è gratuito in tutta la zona. "
            "Potete parcheggiare davanti alla struttura o nelle vicinanze."
        ),
        "sk": (
            "PARKOVANIE\n"
            "Parkovanie je v celej zóne bezplatné. "
            "Môžete zaparkovať pred objektom alebo v blízkosti."
        ),
        "uk": (
            "ПАРКУВАННЯ\n"
            "Паркування на всій території безкоштовне. "
            "Можете припаркуватися перед об'єктом або поруч."
        ),
    },
    "documents": {
        "fr": (
            "CHECK-IN & DOCUMENTS\n"
            "Le check-in est en libre-service à partir de {check_in_time}. "
            "Veuillez préparer les pièces d'identité de tous les adultes pour l'enregistrement "
            "obligatoire (eVisitor). "
            "Pour nous envoyer des photos de vos documents à l'avance, répondez à ce message."
        ),
        "nl": (
            "CHECK-IN & DOCUMENTEN\n"
            "Inchecken verloopt zelfstandig vanaf {check_in_time}. "
            "Houd identiteitsdocumenten van alle volwassen gasten klaar voor de verplichte "
            "registratie (eVisitor). "
            "Wilt u ons vooraf foto's van uw documenten sturen, antwoord dan op dit bericht."
        ),
        "es": (
            "CHECK-IN Y DOCUMENTOS\n"
            "El check-in es autónomo a partir de las {check_in_time}. "
            "Tenga preparados los documentos de identidad de todos los adultos para el registro "
            "obligatorio (eVisitor). "
            "Si desea enviarnos fotos de sus documentos con antelación, responda a este mensaje."
        ),
        "lt": (
            "REGISTRACIJA IR DOKUMENTAI\n"
            "Registracija vyksta savarankiškai nuo {check_in_time}. "
            "Paruoškite visų suaugusių svečių tapatybės dokumentus privalomai registracijai (eVisitor). "
            "Jei norite iš anksto atsiųsti dokumentų nuotraukas, atsakykite į šį pranešimą."
        ),
        "it": (
            "CHECK-IN E DOCUMENTI\n"
            "Il check-in è autonomo dalle {check_in_time}. "
            "Tenete pronti i documenti d'identità di tutti gli ospiti adulti per la registrazione "
            "obbligatoria (eVisitor). "
            "Per inviarci in anticipo le foto dei documenti, rispondete a questo messaggio."
        ),
        "sk": (
            "CHECK-IN A DOKUMENTY\n"
            "Check-in prebieha samostatne od {check_in_time}. "
            "Pripravte si doklady totožnosti všetkých dospelých hostí pre povinnú registráciu (eVisitor). "
            "Ak nám chcete vopred poslať fotografie dokladov, odpovedzte na túto správu."
        ),
        "uk": (
            "ЗАЇЗД І ДОКУМЕНТИ\n"
            "Самостійний заїзд з {check_in_time}. "
            "Підготуйте документи всіх дорослих гостей для обов'язкової реєстрації (eVisitor). "
            "Щоб надіслати фото документів заздалегідь, відповідайте на це повідомлення."
        ),
    },
    "checkout": {
        "fr": (
            "CHECK-OUT (avant 11:00)\n"
            "Veuillez laisser la clé dans la porte de la chambre avant votre départ."
        ),
        "nl": (
            "CHECK-OUT (vóór 11:00)\n"
            "Laat de sleutel in de kamerdeur achter voor vertrek."
        ),
        "es": (
            "CHECK-OUT (antes de las 11:00)\n"
            "Deje la llave en la puerta de la habitación antes de marcharse."
        ),
        "lt": (
            "IŠREGISTRAVIMAS (iki 11:00)\n"
            "Prašome palikti raktą kambario duryse prieš išvykstant."
        ),
        "it": (
            "CHECK-OUT (entro le 11:00)\n"
            "Lasciate la chiave nella porta della camera prima della partenza."
        ),
        "sk": (
            "CHECK-OUT (do 11:00)\n"
            "Pred odchodom nechajte kľúč vo dverách izby."
        ),
        "uk": (
            "ВИЇЗД (до 11:00)\n"
            "Будь ласка, залиште ключ у дверях номера перед від'їздом."
        ),
    },
    "contact": {
        "fr": (
            "QUESTIONS OU ARRIVÉE TARDIVE\n"
            "Écrivez-nous ici ou appelez : {contact_phone}."
        ),
        "nl": (
            "VRAGEN OF LATE AANKOMST\n"
            "Stuur ons een bericht of bel: {contact_phone}."
        ),
        "es": (
            "PREGUNTAS O LLEGADA TARDÍA\n"
            "Escríbanos aquí o llame al: {contact_phone}."
        ),
        "lt": (
            "KLAUSIMAI AR VĖLYVAS ATVYKIMAS\n"
            "Rašykite mums čia arba skambinkite: {contact_phone}."
        ),
        "it": (
            "DOMANDE O ARRIVO TARDIVO\n"
            "Scriveteci qui o chiamate: {contact_phone}."
        ),
        "sk": (
            "OTÁZKY ALEBO NESKORÝ PRÍCHOD\n"
            "Napíšte nám tu alebo zavolajte: {contact_phone}."
        ),
        "uk": (
            "ПИТАННЯ АБО ПІЗНІЙ ПРИЇЗД\n"
            "Напишіть нам тут або зателефонуйте: {contact_phone}."
        ),
    },
}

EXTRA_STEP_CAPTIONS: list[dict[str, str]] = [
    {
        "fr": "Plaque bleue avec le numéro 58 à gauche du portail noir.",
        "nl": "Blauwe plaquette met nummer 58 links van de zwarte poort.",
        "es": "Placa azul con el número 58 a la izquierda del portón negro.",
        "lt": "Mėlyna lentelė su numeriu 58 kairėje juodų vartų pusėje.",
        "it": "Targa blu con il numero 58 sul lato sinistro del cancello nero.",
        "sk": "Modrá tabuľka s číslom 58 na ľavej strane čiernej brány.",
        "uk": "Синя табличка з номером 58 ліворуч від чорних воріт.",
    },
    {
        "fr": "Enseigne « Restaurant Uzorita » / « Uzorita Rooms » et numéro 58.",
        "nl": "Bord « Restaurant Uzorita » / « Uzorita Rooms » en huisnummer 58.",
        "es": "Cartel « Restaurant Uzorita » / « Uzorita Rooms » y número 58.",
        "lt": "Lenta « Restaurant Uzorita » / « Uzorita Rooms » ir numeris 58.",
        "it": "Insegna « Restaurant Uzorita » / « Uzorita Rooms » e numero civico 58.",
        "sk": "Tabuľa « Restaurant Uzorita » / « Uzorita Rooms » a číslo domu 58.",
        "uk": "Табличка « Restaurant Uzorita » / « Uzorita Rooms » і номер 58.",
    },
    {
        "fr": "Traversez le portail et le passage étroit jusqu'à la cour intérieure.",
        "nl": "Loop door de poort en de smalle doorgang naar de binnenplaats.",
        "es": "Pase por el portón y el pasaje estrecho hasta el patio interior.",
        "lt": "Eikite pro vartus ir siaurą koridorių į vidinį kiemą.",
        "it": "Attraversate il cancello e il passaggio stretto fino al cortile interno.",
        "sk": "Prejdite bránou a úzkym priechodom do vnútorného dvora.",
        "uk": "Пройдіть через ворота й вузький прохід до внутрішнього дворика.",
    },
    {
        "fr": "Vitrine en bois contre le mur — ouvrez la porte pour les clés.",
        "nl": "Houten vitrine tegen de muur — open de deur voor de sleutels.",
        "es": "Vitrina de madera junto al muro — abra la puerta para las llaves.",
        "lt": "Medinė vitrina prie sienos — atidarykite duris dėl raktų.",
        "it": "Vetrina in legno contro il muro — aprite lo sportello per le chiavi.",
        "sk": "Drevená vitrína pri múre — otvorte dvere pre kľúče.",
        "uk": "Дерев'яна вітрина біля стіни — відчиніть двері за ключами.",
    },
    {
        "fr": "Les clés des chambres sont accrochées à l'intérieur.",
        "nl": "Kamersleutels hangen binnen aan sleutelhangers.",
        "es": "Las llaves de las habitaciones cuelgan en el interior.",
        "lt": "Kambarių raktai kabo viduje ant pakabukų.",
        "it": "Le chiavi delle camere sono appese all'interno.",
        "sk": "Kľúče od izieb visia vo vnútri na kľúčeniciach.",
        "uk": "Ключі від номерів висять всередині на брелоках.",
    },
    {
        "fr": "Prenez la clé numérotée {key_label} (chambre {room_code}).",
        "nl": "Neem de sleutel met label {key_label} (kamer {room_code}).",
        "es": "Tome la llave con etiqueta {key_label} (habitación {room_code}).",
        "lt": "Paimkite raktą su pakabuku {key_label} (kambarys {room_code}).",
        "it": "Prendete la chiave con etichetta {key_label} (camera {room_code}).",
        "sk": "Vezmite kľúč s príveskom {key_label} (izba {room_code}).",
        "uk": "Візьміть ключ із брелоком {key_label} (номер {room_code}).",
    },
    {
        "fr": "Escaliers en pierre dans la cour menant aux chambres.",
        "nl": "Stenen trap op de binnenplaats leidt naar de gastenkamers.",
        "es": "Escaleras de piedra en el patio suben a las habitaciones.",
        "lt": "Akmeniniai laiptai kieme veda į svečių kambarius.",
        "it": "Scale in pietra nel cortile portano alle camere degli ospiti.",
        "sk": "Kamenné schody na dvore vedú hore k hosťovským izbám.",
        "uk": "Кам'яні сходи у дворі ведуть до гостьових номерів.",
    },
    {
        "fr": "Votre chambre est {room_code} — en haut des escaliers.",
        "nl": "Uw kamer is {room_code} — de trap op.",
        "es": "Su habitación es {room_code} — arriba por las escaleras.",
        "lt": "Jūsų kambarys — {room_code}, aukštyn laiptais.",
        "it": "La vostra camera è {room_code} — su per le scale.",
        "sk": "Vaša izba je {room_code} — hore po schodoch.",
        "uk": "Ваш номер — {room_code}, сходами вгору.",
    },
]

EXTRA_BREAKFAST_HOURS: dict[str, str] = {
    lang: "7:30–9:30" for lang in EXTRA_GUIDE_LANGS
}


def apply_extra_guide_translations(guide: dict) -> None:
    """Merge manual translations into guide sections and step captions in place."""
    sections = guide.get("sections") or {}
    for section_key, langs in EXTRA_GUIDE_SECTIONS.items():
        block = sections.setdefault(section_key, {})
        if isinstance(block, dict):
            block.update(langs)

    steps = guide.get("steps") or []
    for idx, captions in enumerate(EXTRA_STEP_CAPTIONS):
        if idx >= len(steps):
            break
        caption = steps[idx].get("caption")
        if isinstance(caption, dict):
            caption.update(captions)


def apply_extra_breakfast_fact(facts: dict) -> None:
    breakfast = facts.setdefault("breakfast", {})
    if isinstance(breakfast, dict):
        breakfast.update(EXTRA_BREAKFAST_HOURS)
