"""LLM provider for guest message compose."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SEC = 30.0


class GuestComposeError(Exception):
    """LLM compose failed (config, timeout, or API error)."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def llm_configured() -> bool:
    provider = _env("GUEST_COMPOSE_LLM_PROVIDER", "openai").lower()
    api_key = _env("GUEST_COMPOSE_LLM_API_KEY")
    return provider == "openai" and bool(api_key)


def llm_model() -> str:
    return _env("GUEST_COMPOSE_LLM_MODEL", DEFAULT_MODEL)


def llm_timeout() -> float:
    raw = _env("GUEST_COMPOSE_LLM_TIMEOUT_SEC")
    if not raw:
        return DEFAULT_TIMEOUT_SEC
    try:
        return max(5.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SEC


def prompt_version() -> str:
    return _env("GUEST_COMPOSE_PROMPT_VERSION", "v1")


def complete_chat(system: str, user: str, *, model: str | None = None, timeout: float | None = None) -> str:
    """Call OpenAI chat/completions and return assistant text."""
    provider = _env("GUEST_COMPOSE_LLM_PROVIDER", "openai").lower()
    if provider != "openai":
        raise GuestComposeError(f"Unsupported LLM provider: {provider}")

    api_key = _env("GUEST_COMPOSE_LLM_API_KEY")
    if not api_key:
        raise GuestComposeError("GUEST_COMPOSE_LLM_API_KEY is not configured")

    payload = {
        "model": model or llm_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout_sec = timeout if timeout is not None else llm_timeout()

    try:
        response = httpx.post(
            OPENAI_CHAT_URL,
            json=payload,
            headers=headers,
            timeout=timeout_sec,
        )
    except httpx.TimeoutException as exc:
        raise GuestComposeError("LLM request timed out") from exc
    except httpx.HTTPError as exc:
        raise GuestComposeError(f"LLM HTTP error: {exc}") from exc

    if response.status_code == 401:
        raise GuestComposeError("LLM API unauthorized (check API key)")
    if response.status_code == 429:
        raise GuestComposeError("LLM rate limit exceeded")
    if response.status_code >= 400:
        logger.warning(
            "LLM API error",
            extra={"status": response.status_code, "body": response.text[:500]},
        )
        raise GuestComposeError(f"LLM API error ({response.status_code})")

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GuestComposeError("Unexpected LLM response shape") from exc

    text = (content or "").strip()
    if not text:
        raise GuestComposeError("LLM returned empty message")
    return text
