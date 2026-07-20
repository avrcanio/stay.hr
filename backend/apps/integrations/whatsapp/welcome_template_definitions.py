from __future__ import annotations

from dataclasses import dataclass

from apps.integrations.whatsapp.welcome_template import DEFAULT_WELCOME_TEMPLATES

FOOTER = "Managed by stay.hr — https://stay.hr/"

DEFAULT_WELCOME_HEADER_IMAGE_URL = "https://stay.hr/static/whatsapp-header.png"

EXAMPLE_FIRST_NAME = "Hrvoje"
EXAMPLE_BOOKING_CODE = "6489463094"
EXAMPLE_PROPERTY_NAME = "Uzorita B&B"
EXAMPLE_CHECK_IN = "2026-06-20 od 15:00"
EXAMPLE_CHECK_OUT = "2026-06-21 do 11:00"


@dataclass(frozen=True)
class WelcomeTemplateDefinition:
    name: str
    language: str
    body_text: str
    button_text: str


def _body(
    *,
    greeting: str,
    welcome_line: str,
    reservation_line: str,
    cta_line: str,
) -> str:
    return (
        f"{greeting}\n\n"
        f"{welcome_line}\n\n"
        f"{reservation_line}\n\n"
        f"{cta_line}\n\n"
        f"{FOOTER}"
    )


WELCOME_TEMPLATE_DEFINITIONS: dict[str, WelcomeTemplateDefinition] = {
    "hr": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["hr"],
        language="hr",
        body_text=_body(
            greeting="Bok {{1}}!",
            welcome_line="Dobrodošli u Stay.hr.",
            reservation_line="Rezervacija {{2}} u {{3}} ({{4}} – {{5}}).",
            cta_line=(
                "Autocheck-in možete pokrenuti odmah – uštedite vrijeme na recepciji."
            ),
        ),
        button_text="Auto check in",
    ),
    "en": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["en"],
        language="en",
        body_text=_body(
            greeting="Hi {{1}}!",
            welcome_line="Welcome to Stay.hr.",
            reservation_line="Booking {{2}} at {{3}} ({{4}} – {{5}}).",
            cta_line="You can start autocheck-in now — save time at reception.",
        ),
        button_text="Auto check-in",
    ),
    "de": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["de"],
        language="de",
        body_text=_body(
            greeting="Guten Tag {{1}}!",
            welcome_line="Willkommen bei Stay.hr.",
            reservation_line="Buchung {{2}} in {{3}} ({{4}} – {{5}}).",
            cta_line=(
                "Starten Sie jetzt den Autocheck-in — sparen Sie Zeit an der Rezeption."
            ),
        ),
        button_text="Autocheck-in",
    ),
    "es": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["es"],
        language="es",
        body_text=_body(
            greeting="¡Hola {{1}}!",
            welcome_line="Bienvenido/a a Stay.hr.",
            reservation_line="Reserva {{2}} en {{3}} ({{4}} – {{5}}).",
            cta_line=(
                "Puede iniciar el autocheck-in ahora — ahorre tiempo en recepción."
            ),
        ),
        button_text="Auto check-in",
    ),
    "fr": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["fr"],
        language="fr",
        body_text=_body(
            greeting="Bonjour {{1}} !",
            welcome_line="Bienvenue sur Stay.hr.",
            reservation_line="Réservation {{2}} à {{3}} ({{4}} – {{5}}).",
            cta_line=(
                "Vous pouvez lancer l'autocheck-in maintenant — "
                "gagnez du temps à l'accueil."
            ),
        ),
        button_text="Auto check-in",
    ),
    "hu": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["hu"],
        language="hu",
        body_text=_body(
            greeting="Szia {{1}}!",
            welcome_line="Üdvözöljük a Stay.hr-nál.",
            reservation_line="Foglalás {{2}} — {{3}} ({{4}} – {{5}}).",
            cta_line=(
                "Az autocheck-in-t most elindíthatja — időt takarít meg a recepción."
            ),
        ),
        button_text="Autocheck-in",
    ),
    "cs": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["cs"],
        language="cs",
        body_text=_body(
            greeting="Ahoj {{1}}!",
            welcome_line="Vítejte ve Stay.hr.",
            reservation_line="Rezervace {{2}} v {{3}} ({{4}} – {{5}}).",
            cta_line="Autocheck-in můžete spustit hned — ušetříte čas na recepci.",
        ),
        button_text="Autocheck-in",
    ),
    "ro": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["ro"],
        language="ro",
        body_text=_body(
            greeting="Bună {{1}}!",
            welcome_line="Bine ați venit la Stay.hr.",
            reservation_line="Rezervarea {{2}} la {{3}} ({{4}} – {{5}}).",
            cta_line=(
                "Puteți începe autocheck-in-ul acum — economisiți timp la recepție."
            ),
        ),
        button_text="Autocheck-in",
    ),
    "ua": WelcomeTemplateDefinition(
        name=DEFAULT_WELCOME_TEMPLATES["ua"],
        language="uk",
        body_text=_body(
            greeting="Вітаємо, {{1}}!",
            welcome_line="Ласкаво просимо до Stay.hr.",
            reservation_line="Бронювання {{2}} у {{3}} ({{4}} – {{5}}).",
            cta_line=(
                "Ви можете розпочати autocheck-in зараз — заощадьте час на ресепції."
            ),
        ),
        button_text="Autocheck-in",
    ),
}


def example_body_parameters() -> list[str]:
    return [
        EXAMPLE_FIRST_NAME,
        EXAMPLE_BOOKING_CODE,
        EXAMPLE_PROPERTY_NAME,
        EXAMPLE_CHECK_IN,
        EXAMPLE_CHECK_OUT,
    ]


def build_welcome_template_payload(
    definition: WelcomeTemplateDefinition,
    *,
    header_handle: str | None,
) -> dict:
    components: list[dict] = []
    if header_handle:
        components.append(
            {
                "type": "HEADER",
                "format": "IMAGE",
                "example": {"header_handle": [header_handle]},
            }
        )
    components.extend(
        [
            {
                "type": "BODY",
                "text": definition.body_text,
                "example": {"body_text": [example_body_parameters()]},
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "QUICK_REPLY",
                        "text": definition.button_text,
                    }
                ],
            },
        ]
    )
    return {
        "name": definition.name,
        "language": definition.language,
        "category": "UTILITY",
        "parameter_format": "POSITIONAL",
        "allow_category_change": True,
        "components": components,
    }
