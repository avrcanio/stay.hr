from __future__ import annotations

from uuid import UUID

from apps.billing.exceptions import FiscalizationError
from apps.billing.models import Invoice, TenantFiscalSettings
from apps.billing.services.fisk1 import FiscalResult
from apps.billing.services.fiskal_platform.client import FiskalExecutionClient
from apps.billing.services.fiskal_platform.credentials import (
    build_provider_credentials,
    build_provider_options,
)
from apps.billing.services.fiskal_platform.payload import build_guest_invoice_f1_payload


def _build_execution_body(invoice: Invoice, settings: TenantFiscalSettings) -> dict:
    return {
        "operation": "fiscalize",
        "provider": "pu_cis",
        "issuer": {"country": "HR", "legal_id": settings.issuer_oib},
        "tenant_key": invoice.tenant.slug,
        "source_application": "stay",
        "document_type": "invoice",
        "schema_name": "guest-invoice-f1-v1",
        "schema_version": "1.0",
        "idempotency_key": f"stay-invoice-{invoice.pk}",
        "external_reference": invoice.invoice_number,
        "provider_credentials": build_provider_credentials(settings),
        "provider_options": build_provider_options(settings),
        "payload": build_guest_invoice_f1_payload(invoice, settings),
    }


def submit_guest_invoice_fiscalization(
    invoice: Invoice,
    settings: TenantFiscalSettings,
    *,
    client: FiskalExecutionClient | None = None,
) -> UUID:
    owns_client = client is None
    client = client or FiskalExecutionClient()
    idempotency_key = f"stay-invoice-{invoice.pk}"
    try:
        result = client.submit_execution(
            _build_execution_body(invoice, settings),
            idempotency_key=idempotency_key,
            correlation_id=f"stay-invoice-{invoice.pk}",
        )
        return result.request_id
    finally:
        if owns_client:
            client.close()


def fiscalize_via_platform(
    invoice: Invoice,
    settings: TenantFiscalSettings,
    *,
    client: FiskalExecutionClient | None = None,
) -> FiscalResult:
    owns_client = client is None
    client = client or FiskalExecutionClient()
    request_id: UUID | None = None
    try:
        request_id = submit_guest_invoice_fiscalization(
            invoice,
            settings,
            client=client,
        )
        status = client.poll_until_terminal(request_id)
        if status.status == "accepted":
            if not status.jir:
                raise FiscalizationError(
                    f"Fiskal execution accepted without JIR (request_id={request_id})",
                    fiskal_request_id=request_id,
                )
            return FiscalResult(
                jir=status.jir,
                request_snapshot=f"fiskal_request_id={request_id}",
                response_snapshot=(
                    f"status={status.status}; jir={status.jir}; zki={status.zki or ''}"
                ),
                fiskal_request_id=request_id,
            )

        error_parts = [status.status]
        if status.error_code:
            error_parts.append(status.error_code)
        if status.error_message:
            error_parts.append(status.error_message)
        raise FiscalizationError(
            f"Fiskal execution failed ({', '.join(error_parts)}, request_id={request_id})",
            fiskal_request_id=request_id,
        )
    finally:
        if owns_client:
            client.close()
