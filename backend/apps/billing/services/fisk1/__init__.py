from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.billing.models import Invoice


@dataclass(frozen=True)
class FiscalResult:
    jir: str
    request_snapshot: str = ""
    response_snapshot: str = ""


class FiscalizationConnector:
    def fiscalize(self, invoice: Invoice, settings) -> FiscalResult:
        raise NotImplementedError
