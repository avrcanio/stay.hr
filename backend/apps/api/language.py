from __future__ import annotations

SUPPORTED_APP_LANGS = frozenset({"hr", "en", "es", "fr", "de", "it"})


def normalize_app_language(raw: str | None) -> str:
    if not raw:
        return "en"
    base = raw.split("-")[0].strip().lower()
    if base in SUPPORTED_APP_LANGS:
        return base
    return "en"


def resolve_request_language(request, *, tenant=None) -> str:
    """UI language from ?lang=, Accept-Language, or tenant default."""
    query_lang = (request.query_params.get("lang") or "").strip()
    if query_lang:
        return normalize_app_language(query_lang)

    header = (request.headers.get("Accept-Language") or "").strip()
    if header:
        return normalize_app_language(header.split(",")[0])

    if tenant is not None:
        default = getattr(tenant, "default_language", None)
        if default:
            return normalize_app_language(str(default))

    return "hr"


def parse_translate_flag(raw: str | None, *, default: bool = True) -> bool:
    """Whether to localize review text for the resolved UI language."""
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in ("0", "false", "no", "off"):
        return False
    if value in ("1", "true", "yes", "on"):
        return True
    return default
