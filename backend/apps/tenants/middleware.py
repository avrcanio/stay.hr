from django.conf import settings

from apps.tenants.models import TenantDomain

_INTERNAL_HOSTS = frozenset({"stay-django", "localhost", "127.0.0.1"})


def resolve_tenant_host(request) -> str:
    """Public booking host from Host or X-Forwarded-Host (BFF internal fetch)."""
    raw_host = (request.META.get("HTTP_HOST") or "").split(":")[0].lower()
    forwarded = (request.META.get("HTTP_X_FORWARDED_HOST") or "").split(",")[0].strip()
    if forwarded:
        forwarded = forwarded.split(":")[0].lower()
    # Internal BFF uses stay-django alias; trust X-Forwarded-Host for tenant resolution.
    if raw_host in _INTERNAL_HOSTS and forwarded:
        return forwarded
    return request.get_host().split(":")[0].lower()


class TenantHostMiddleware:
    """Resolve request.tenant from Host header via TenantDomain."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "tenant", None) is None:
            host = resolve_tenant_host(request)
            domains = TenantDomain.objects.select_related(
                "tenant",
                "property",
            ).filter(domain=host)
            if not settings.DEBUG:
                domains = domains.filter(is_verified=True)
            domain = domains.first()
            if domain is not None:
                request.tenant = domain.tenant
                request.tenant_domain = domain
        return self.get_response(request)
