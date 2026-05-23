class SmoobuConfigError(Exception):
    pass


class SmoobuApiError(Exception):
    pass


class SmoobuRatesError(Exception):
    pass


class SmoobuBlockConflictError(SmoobuRatesError):
    """Smoobu rejected a block because dates are unavailable (overlap / conflict)."""
    pass


class SmoobuBookingIngestError(Exception):
    pass
