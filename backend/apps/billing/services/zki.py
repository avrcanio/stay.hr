from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal


def format_amount_for_zki(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    return f"{quantized:.2f}".replace(".", ",")


def format_datetime_for_zki(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def calculate_zki(
    *,
    oib: str,
    issued_at: datetime,
    invoice_number: str,
    business_premise_code: str,
    payment_device_code: str,
    total: Decimal,
) -> str:
    """Calculate Zaštitni kod izdavatelja (MD5 hex digest)."""
    payload = (
        f"{oib.strip()}"
        f"{format_datetime_for_zki(issued_at)}"
        f"{invoice_number.strip()}"
        f"{business_premise_code.strip()}"
        f"{payment_device_code.strip()}"
        f"{format_amount_for_zki(total)}"
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()
