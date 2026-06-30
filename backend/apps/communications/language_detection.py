"""Heuristic guest message language detection."""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMOJI_ONLY = re.compile(
    r"^[\s\U0001F300-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]+$"
)


@dataclass(frozen=True)
class DetectionResult:
    language: str
    confidence: float


def _has_confidence(language: str) -> float:
    return 0.85 if language != "unknown" else 0.0


def detect(text: str) -> DetectionResult:
    """Best-effort language from inbound guest message text."""
    lowered = (text or "").lower()
    stripped = lowered.strip()
    if not stripped:
        return DetectionResult(language="unknown", confidence=0.0)
    if _EMOJI_ONLY.match(stripped):
        return DetectionResult(language="unknown", confidence=0.0)

    sk_markers = (
        "ľ",
        "ô",
        "ŕ",
        "veľk",
        "izba",
        "záchod",
        "ďakuj",
        "špinav",
        "kúpeľ",
        "ste ",
        "sme ",
        "prie",
    )
    if any(marker in lowered for marker in sk_markers):
        return DetectionResult(language="sk", confidence=_has_confidence("sk"))

    de_markers = (
        "ß",
        "schön",
        "danke",
        "zimmer",
        "übernacht",
        "gäste",
        "spät",
        "ankunft",
        "können",
        "spaeter",
    )
    if any(marker in lowered for marker in de_markers):
        return DetectionResult(language="de", confidence=_has_confidence("de"))

    hr_markers = (
        "hvala",
        "soba",
        "boravak",
        "gost",
        "žao",
        "čist",
        "dolaz",
        "doći",
        "možemo",
        "večer",
        "vecer",
        "kasnij",
    )
    if any(marker in lowered for marker in hr_markers):
        return DetectionResult(language="hr", confidence=_has_confidence("hr"))

    es_markers = ("gracias", "habitación", "llegada", "tarde", "noche", "podemos")
    if any(marker in lowered for marker in es_markers):
        return DetectionResult(language="es", confidence=_has_confidence("es"))

    fr_markers = ("merci", "chambre", "arrivée", "arrivee", "soir", "tard", "pouvons")
    if any(marker in lowered for marker in fr_markers):
        return DetectionResult(language="fr", confidence=_has_confidence("fr"))

    it_markers = ("grazie", "camera", "arrivo", "sera", "tardi", "possiamo", "parcheggio")
    if any(marker in lowered for marker in it_markers):
        return DetectionResult(language="it", confidence=_has_confidence("it"))

    pl_markers = ("dziękuj", "dzieku", "pokój", "pokoj", "przyjazd", "późn", "pozn", "możemy", "mozemy")
    if any(marker in lowered for marker in pl_markers):
        return DetectionResult(language="pl", confidence=_has_confidence("pl"))

    ro_markers = ("mulțum", "multum", "cameră", "camera", "sosire", "seară", "seara", "putem")
    if any(marker in lowered for marker in ro_markers):
        return DetectionResult(language="ro", confidence=_has_confidence("ro"))

    nl_markers = ("dank", "kamer", "aankomst", "avond", "laat", "kunnen", "parkeer")
    if any(marker in lowered for marker in nl_markers):
        return DetectionResult(language="nl", confidence=_has_confidence("nl"))

    cs_markers = ("děkuj", "deku", "pokoj", "příjezd", "prijezd", "večer", "vecer", "můžeme", "muzeme")
    if any(marker in lowered for marker in cs_markers):
        return DetectionResult(language="cs", confidence=_has_confidence("cs"))

    pt_markers = ("obrigad", "quarto", "chegada", "noite", "tarde", "podemos", "estacionamento")
    if any(marker in lowered for marker in pt_markers):
        return DetectionResult(language="pt", confidence=_has_confidence("pt"))

    hu_markers = ("köszön", "koszon", "szoba", "érkez", "erkez", "este", "késő", "keso")
    if any(marker in lowered for marker in hu_markers):
        return DetectionResult(language="hu", confidence=_has_confidence("hu"))

    return DetectionResult(language="en", confidence=0.35)
