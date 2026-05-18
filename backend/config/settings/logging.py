import logging


class SensitiveHeaderFilter(logging.Filter):
    """Redact API keys and bearer tokens from log records."""

    _SENSITIVE_MARKERS = (
        "authorization:",
        "x-stay-app-key:",
        "bearer ",
        "stay_pk_live_",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        for marker in self._SENSITIVE_MARKERS:
            if marker in message:
                record.msg = "[REDACTED]"
                record.args = ()
                break
        return True
