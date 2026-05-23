from rest_framework.permissions import BasePermission

from apps.tenants.models import TenantMembership

ADMIN_SCOPES = frozenset({"admin:read", "admin:write"})
RECEPTION_SCOPES = frozenset({"reception:read", "reception:write"})


class HasReceptionAccess(BasePermission):
    """ApiApplication with required scopes, or authenticated staff with tenant session."""

    def has_permission(self, request, view) -> bool:
        application = getattr(request, "api_application", None)
        required = getattr(view, "required_scopes", None) or []

        if application is not None:
            granted = set(application.scopes or [])
            return all(scope in granted for scope in required)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not user.is_staff:
            return False

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return False
        if user.is_superuser:
            return True
        return TenantMembership.objects.filter(user=user, tenant=tenant).exists()


class HasApiApplication(BasePermission):
    def has_permission(self, request, view) -> bool:
        return getattr(request, "api_application", None) is not None


class HasScope(BasePermission):
    """Require all scopes listed on the view (view.required_scopes)."""

    def has_permission(self, request, view) -> bool:
        application = getattr(request, "api_application", None)
        if application is None:
            return False
        required = getattr(view, "required_scopes", None) or []
        granted = set(application.scopes or [])
        return all(scope in granted for scope in required)


class DenyAdminScopes(BasePermission):
    """Block tokens that carry admin scopes on public/mobile endpoints."""

    message = "Admin scopes are not allowed on this endpoint."

    def has_permission(self, request, view) -> bool:
        application = getattr(request, "api_application", None)
        if application is None:
            return True
        granted = set(application.scopes or [])
        return not granted.intersection(ADMIN_SCOPES)
