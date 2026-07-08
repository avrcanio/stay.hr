from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpResponseNotFound
from django.middleware.csrf import CsrfViewMiddleware

from apps.tenants.models import TenantDomain

_INTERNAL_HOSTS = frozenset({"stay-django", "localhost", "127.0.0.1"})
PLATFORM_ADMIN_HOSTS = frozenset({"admin.stay.hr", "api.stay.hr"})


def resolve_tenant_host(request) -> str:
    """
    Public booking host from Host or X-Forwarded-Host (BFF internal fetch).

    Trust model: X-Forwarded-Host is used only when HTTP_HOST is an internal
    alias (stay-django, localhost). Public requests use HTTP_HOST directly,
    so clients cannot spoof tenant via X-Forwarded-Host through Traefik.
    """
    raw_host = (request.META.get("HTTP_HOST") or "").split(":")[0].lower()
    forwarded = (request.META.get("HTTP_X_FORWARDED_HOST") or "").split(",")[0].strip()
    if forwarded:
        forwarded = forwarded.split(":")[0].lower()
    # Internal BFF uses stay-django alias; trust X-Forwarded-Host for tenant resolution.
    if raw_host in _INTERNAL_HOSTS and forwarded:
        return forwarded
    if raw_host:
        return raw_host
    return request.get_host().split(":")[0].lower()


def is_verified_tenant_domain(host: str) -> bool:
    host = (host or "").split(":")[0].lower()
    if not host:
        return False
    qs = TenantDomain.objects.filter(domain=host)
    if not settings.DEBUG:
        qs = qs.filter(is_verified=True)
    return qs.exists()


class TenantDomainAllowedHostMiddleware:
    """Allow verified tenant booking domains not listed in DJANGO_ALLOWED_HOSTS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = resolve_tenant_host(request)
        if host and host not in settings.ALLOWED_HOSTS and is_verified_tenant_domain(host):
            settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, host]
        return self.get_response(request)


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


class AdminTenantHostGuardMiddleware:
    """Block /admin on unknown non-platform hosts."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin"):
            host = resolve_tenant_host(request)
            if host not in PLATFORM_ADMIN_HOSTS and getattr(request, "tenant", None) is None:
                return HttpResponseNotFound()
        return self.get_response(request)


class TenantDomainCsrfMiddleware(CsrfViewMiddleware):
    """Accept CSRF from verified tenant booking domains."""

    def _origin_verified(self, request):
        if super()._origin_verified(request):
            return True
        origin = request.META.get("HTTP_ORIGIN")
        if origin and self._is_verified_tenant_origin(origin):
            return True
        referer = request.META.get("HTTP_REFERER")
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme and parsed.hostname:
                origin_from_referer = f"{parsed.scheme}://{parsed.hostname}"
                if parsed.port:
                    origin_from_referer = f"{origin_from_referer}:{parsed.port}"
                if self._is_verified_tenant_origin(origin_from_referer):
                    return True
        return False

    @staticmethod
    def _is_verified_tenant_origin(origin: str) -> bool:
        parsed = urlparse(origin)
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        if parsed.scheme == "https":
            return is_verified_tenant_domain(host)
        if parsed.scheme == "http" and settings.DEBUG:
            return is_verified_tenant_domain(host)
        return False
