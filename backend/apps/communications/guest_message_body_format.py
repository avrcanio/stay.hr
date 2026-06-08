"""Format guest message body_text for chat timeline (Flutter / reception)."""

from __future__ import annotations

import html
import re

BOOKING_REPLY_LINE_RE = re.compile(
    r"^#+\s*-?\s*please type your reply above this line\s*-?\s*#+\s*$",
    re.IGNORECASE | re.MULTILINE,
)
BOOKING_DISCLAIMER_RE = re.compile(
    r"The accommodation provider takes full responsibility for the content of this message, sent through Booking\.com\.?\s*",
    re.IGNORECASE,
)
BOOKING_PRIVACY_FOOTER_RE = re.compile(
    r"\*?\s*Booking\.com will receive and process replies to this email.*",
    re.IGNORECASE | re.DOTALL,
)
BOOKING_CONFIRMATION_HEADER_RE = re.compile(
    r"^\s*Confirmation number:\s*\d+\s*",
    re.IGNORECASE | re.MULTILINE,
)
BOOKING_GUEST_MESSAGE_HEADER_RE = re.compile(
    r"You have a new message from a guest\s*",
    re.IGNORECASE,
)
HTML_BREAK_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
HTML_BLOCK_END_RE = re.compile(r"</\s*(p|div|tr|li|h[1-6])\s*>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_plain(text: str) -> str:
    if "<" not in text or ">" not in text:
        return text
    normalized = HTML_BREAK_RE.sub("\n", text)
    normalized = HTML_BLOCK_END_RE.sub("\n\n", normalized)
    normalized = HTML_TAG_RE.sub("", normalized)
    return html.unescape(normalized)


def strip_booking_email_boilerplate(text: str) -> str:
    """Remove Booking.com relay headers/footers; keep property message."""
    cleaned = (text or "").replace("\r\n", "\n")
    cleaned = _html_to_plain(cleaned)
    cleaned = BOOKING_REPLY_LINE_RE.sub("", cleaned)
    cleaned = BOOKING_DISCLAIMER_RE.sub("", cleaned)
    cleaned = BOOKING_PRIVACY_FOOTER_RE.sub("", cleaned)
    cleaned = BOOKING_CONFIRMATION_HEADER_RE.sub("", cleaned)
    cleaned = BOOKING_GUEST_MESSAGE_HEADER_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _reflow_single_line_paragraphs(text: str) -> str:
    """Insert paragraph breaks into a long single-line message."""
    if not text or "\n" in text:
        return text
    if len(text) < 120:
        return text

    parts: list[str] = []
    rest = text.strip()

    greeting_match = re.match(
        r"^((?:Poštovan[ai]|Pozdrav|Dear|Hello|Hi|Hallo|Bonjour)[^,!]*[,!])\s+",
        rest,
        re.IGNORECASE,
    )
    if greeting_match:
        parts.append(greeting_match.group(1).strip())
        rest = rest[greeting_match.end() :].strip()

    if not rest:
        return "\n\n".join(parts) if parts else text

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZČĆĐŠŽ\"'])", rest)
    if len(sentences) <= 1:
        parts.append(rest)
    else:
        block: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            block.append(sentence)
            if len(" ".join(block)) >= 180:
                parts.append(" ".join(block))
                block = []
        if block:
            parts.append(" ".join(block))

    signature_match = re.search(
        r"\s+(Uzorita[^.]*|Managed by stay\.hr.*|Lijep pozdrav,.*)$",
        parts[-1] if parts else rest,
        re.IGNORECASE,
    )
    if signature_match and parts:
        main = parts[-1][: signature_match.start()].strip()
        signature = parts[-1][signature_match.start() :].strip()
        if main:
            parts[-1] = main
        else:
            parts.pop()
        if signature:
            parts.append(signature)

    return "\n\n".join(part for part in parts if part)


def normalize_timeline_newlines(text: str) -> str:
    """Keep paragraph breaks; collapse spaces/tabs within lines."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    blank = False
    for raw_line in normalized.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            if lines and not blank:
                lines.append("")
            blank = True
            continue
        blank = False
        lines.append(line)
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def normalize_outbound_plain_text(text: str) -> str:
    """Normalize plain text before guest SMTP send (no inbound boilerplate stripping)."""
    cleaned = normalize_timeline_newlines(text)
    if cleaned.count("\n") < 2:
        cleaned = _reflow_single_line_paragraphs(cleaned)
        cleaned = normalize_timeline_newlines(cleaned)
    return cleaned


def format_timeline_body_text(text: str) -> str:
    """Prepare body_text for chat UI (Flutter whitespace-pre-wrap)."""
    cleaned = strip_booking_email_boilerplate(text)
    cleaned = normalize_timeline_newlines(cleaned)
    if cleaned.count("\n") < 2:
        cleaned = _reflow_single_line_paragraphs(cleaned)
        cleaned = normalize_timeline_newlines(cleaned)
    return cleaned


def timeline_body_quality_score(text: str) -> tuple[int, int, int]:
    """Higher is better for merge: newlines, length, inverse boilerplate."""
    formatted = format_timeline_body_text(text)
    newline_count = formatted.count("\n")
    boilerplate_penalty = 0
    lower = (text or "").lower()
    if "accommodation provider takes full responsibility" in lower:
        boilerplate_penalty += 500
    if "booking.com will receive and process" in lower:
        boilerplate_penalty += 200
    return (newline_count, len(formatted), -boilerplate_penalty)
