from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from apps.billing.models import Invoice


@dataclass(frozen=True)
class FiscalResult:
    jir: str
    request_snapshot: str = ""
    response_snapshot: str = ""
    fiskal_request_id: UUID | None = None


class FiscalizationConnector:
    def fiscalize(self, invoice: Invoice, settings) -> FiscalResult:
        raise NotImplementedError
