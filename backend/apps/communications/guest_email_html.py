"""HTML alternative for guest SMTP emails (reception Mail channel)."""

from __future__ import annotations

import html
import re

from apps.communications.guest_message_body_format import normalize_outbound_plain_text

_STAY_FOOTER = "Managed by stay.hr — https://stay.hr/"

_FOOTER_STYLE = 'style="color:#666;font-size:12px;"'


def _paragraph_html(block: str) -> str:
    lines = block.split("\n")
    inner = "<br>\n".join(html.escape(line) for line in lines if line is not None)
    return f"<p>{inner}</p>" if inner else ""


def render_guest_message_email_html(body_text: str) -> str:
    """Convert normalized plain guest message to safe HTML paragraphs."""
    normalized = normalize_outbound_plain_text(body_text)
    if not normalized:
        return ""

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    if not paragraphs:
        paragraphs = [normalized]

    parts: list[str] = []
    for paragraph in paragraphs:
        if paragraph.strip() == _STAY_FOOTER:
            parts.append(f"<p {_FOOTER_STYLE}>{html.escape(_STAY_FOOTER)}</p>")
        elif paragraph.endswith(_STAY_FOOTER) and paragraph != _STAY_FOOTER:
            main = paragraph[: -len(_STAY_FOOTER)].rstrip()
            if main:
                parts.append(_paragraph_html(main))
            parts.append(f"<p {_FOOTER_STYLE}>{html.escape(_STAY_FOOTER)}</p>")
        else:
            rendered = _paragraph_html(paragraph)
            if rendered:
                parts.append(rendered)

    return "\n".join(parts)


def prepare_guest_email_bodies(
    body_text: str,
    *,
    body_html: str | None = None,
) -> tuple[str, str]:
    """Return (normalized plain text, html alternative) for multipart send."""
    text = normalize_outbound_plain_text(body_text)
    html_part = (body_html or "").strip() or render_guest_message_email_html(text)
    return text, html_part
