from django.conf import settings

from apps.tenants.models import TenantDomain


class TenantHostMiddleware:
    """Resolve request.tenant from Host header via TenantDomain."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "tenant", None) is None:
            host = request.get_host().split(":")[0].lower()
            domains = TenantDomain.objects.select_related("tenant").filter(domain=host)
            if not settings.DEBUG:
                domains = domains.filter(is_verified=True)
            domain = domains.first()
            if domain is not None:
                request.tenant = domain.tenant
        return self.get_response(request)
