class BillingError(Exception):
    """Base billing error."""


class InvoiceBuildError(BillingError):
    """Cannot build invoice from reservation."""


class FiscalConfigError(BillingError):
    """Tenant fiscal settings incomplete or invalid."""


class FiscalizationError(BillingError):
    """Fiskalizacija 1.0 request failed."""
