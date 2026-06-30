"""Guest reply language value objects — no logic, no model references."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LanguageSource(str, Enum):
    OVERRIDE = "override"
    REPLY_LANGUAGE = "reply_language"
    MESSAGE = "message"
    CONVERSATION = "conversation"
    COUNTRY = "country"
    TENANT_DEFAULT = "tenant_default"
    FALLBACK = "fallback"


class LanguageMode(str, Enum):
    REACTIVE = "reactive"
    PROACTIVE = "proactive"


@dataclass(frozen=True)
class GuestLanguageContext:
    language: str
    source: LanguageSource
    confidence: float
    mode: LanguageMode
    reason: str = ""
