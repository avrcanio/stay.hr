"""Parse property financial report recipient lists."""

from __future__ import annotations

import re

from django.core.validators import validate_email
from django.core.exceptions import ValidationError

_RECIPIENT_SPLIT = re.compile(r"[,;\s]+")


def parse_financial_report_recipients(raw: str) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    for part in _RECIPIENT_SPLIT.split((raw or "").strip()):
        email = part.strip()
        if not email:
            continue
        try:
            validate_email(email)
        except ValidationError:
            continue
        lowered = email.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        recipients.append(email)
    return recipients
