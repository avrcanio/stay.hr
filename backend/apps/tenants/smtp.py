"""SMTP helpers for per-tenant guest email."""


def smtp_host_for_email(email: str) -> str:
    address = (email or "").strip().lower()
    if "@" not in address:
        return ""
    domain = address.split("@", 1)[1]
    return f"mail.{domain}" if domain else ""
