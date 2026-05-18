from rest_framework.permissions import BasePermission

ADMIN_SCOPES = frozenset({"admin:read", "admin:write"})


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
