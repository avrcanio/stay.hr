from __future__ import annotations

import base64

from apps.billing.exceptions import FiscalizationError
from apps.billing.models import TenantFiscalSettings


def build_provider_credentials(settings: TenantFiscalSettings) -> dict[str, str]:
    if not settings.certificate_file:
        raise FiscalizationError("Tenant fiscal certificate file is missing.")
    password = settings.get_certificate_password()
    if not password:
        raise FiscalizationError("Tenant fiscal certificate password is missing.")

    p12_bytes = settings.certificate_file.read()
    settings.certificate_file.seek(0)
    return {
        "certificate": base64.b64encode(p12_bytes).decode("ascii"),
        "password": password,
    }


def build_provider_options(settings: TenantFiscalSettings) -> dict[str, str]:
    return {
        "cis_env": "pts" if settings.use_test_endpoint else "prod",
    }
