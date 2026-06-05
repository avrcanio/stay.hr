"""Parse identity fields from MRZ text (TD1/TD3)."""

from __future__ import annotations

import re


def _clean_mrz_lines(mrz_text: str) -> list[str]:
    lines: list[str] = []
    for raw in (mrz_text or "").splitlines():
        line = re.sub(r"\s+", "", raw.upper())
        if line:
            lines.append(line)
    return lines


def parse_sex_from_mrz(mrz_text: str) -> str:
    """Return M or F when encoded in MRZ; empty string if unknown."""
    lines = _clean_mrz_lines(mrz_text)
    if not lines:
        return ""

    for line in lines:
        if len(line) >= 44:
            # TD3 passport line 2
            sex = line[20:21]
            if sex in {"M", "F"}:
                return sex
        if 26 <= len(line) <= 36:
            # TD1 ID card line 2 (OCR may truncate filler chars)
            sex = line[7:8]
            if sex in {"M", "F"}:
                return sex

    return ""


def normalize_residence_address(address: str) -> str:
    """eVisitor expects City, street — strip postal code prefix from city segment."""
    raw = (address or "").strip()
    if not raw or "," not in raw:
        return raw

    city_part, rest = raw.split(",", 1)
    city_part = city_part.strip()
    rest = rest.strip()
    match = re.match(r"^(\d{4,5})\s+(.+)$", city_part)
    if match:
        city_part = match.group(2).strip()
    return f"{city_part}, {rest}" if rest else city_part
