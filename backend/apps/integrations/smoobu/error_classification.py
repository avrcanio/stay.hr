"""Classify Smoobu API errors for web booking lifecycle."""

from __future__ import annotations

from apps.integrations.smoobu.exceptions import SmoobuApiError, SmoobuBlockConflictError, SmoobuRatesError


def is_smoobu_block_conflict(exc: Exception) -> bool:
    if isinstance(exc, SmoobuBlockConflictError):
        return True
    if isinstance(exc, SmoobuRatesError):
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "already blocked",
                "not available",
                "overlap",
                "conflict",
                "unavailable",
            )
        )
    if isinstance(exc, SmoobuApiError):
        message = str(exc).lower()
        if any(code in message for code in ("(409)", "(422)", "(400)")):
            return True
        return any(
            token in message
            for token in (
                "not available",
                "overlap",
                "conflict",
                "blocked",
                "unavailable",
            )
        )
    return False
