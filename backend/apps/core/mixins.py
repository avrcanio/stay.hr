from rest_framework.exceptions import NotAuthenticated


class TenantViewMixin:
    """Filter querysets to the authenticated tenant."""

    def get_tenant(self):
        tenant = getattr(self.request, "tenant", None)
        if tenant is None:
            raise NotAuthenticated("Tenant context is required.")
        return tenant

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.for_tenant(self.get_tenant())
