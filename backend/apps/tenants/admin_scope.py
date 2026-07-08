"""Helpers for tenant-scoped Django admin access."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import AnonymousUser

from apps.tenants.middleware import PLATFORM_ADMIN_HOSTS, resolve_tenant_host
from apps.tenants.models import Tenant, TenantMembership


@dataclass(frozen=True)
class AdminScope:
    platform_admin: bool
    tenant_id: int | None


def resolve_admin_scope(request) -> AdminScope:
    host = resolve_tenant_host(request)
    if host in PLATFORM_ADMIN_HOSTS:
        return AdminScope(platform_admin=True, tenant_id=None)
    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        return AdminScope(platform_admin=False, tenant_id=tenant.pk)
    return AdminScope(platform_admin=False, tenant_id=None)


def is_superuser(user) -> bool:
    return bool(user and user.is_authenticated and user.is_superuser)


def is_platform_admin(request) -> bool:
    """Superuser on platform admin host (unscoped multi-tenant access)."""
    scope = resolve_admin_scope(request)
    return scope.platform_admin and is_superuser(request.user)


def get_allowed_tenant_ids(request) -> list[int] | None:
    """
    Return None for unscoped superuser (no filter), or a list of tenant PKs.
    Staff without memberships get an empty list.
    """
    user = request.user
    if not user.is_authenticated:
        return []

    scope = resolve_admin_scope(request)

    if scope.platform_admin:
        if user.is_superuser:
            return None
        if not user.is_staff:
            return []
        return list(
            TenantMembership.objects.filter(user=user).values_list("tenant_id", flat=True),
        )

    if scope.tenant_id is None:
        return []

    if user.is_superuser:
        return [scope.tenant_id]

    if not user.is_staff:
        return []

    member_ids = set(
        TenantMembership.objects.filter(user=user).values_list("tenant_id", flat=True),
    )
    if scope.tenant_id in member_ids:
        return [scope.tenant_id]
    return []


def get_allowed_tenants(request):
    ids = get_allowed_tenant_ids(request)
    if ids is None:
        return Tenant.objects.all()
    if not ids:
        return Tenant.objects.none()
    return Tenant.objects.filter(pk__in=ids)


def user_has_tenant_access(request, tenant_id: int | None) -> bool:
    if tenant_id is None:
        return False
    allowed = get_allowed_tenant_ids(request)
    if allowed is None:
        return True
    return tenant_id in allowed


def staff_has_tenant_membership(request) -> bool:
    user = request.user
    if not user.is_authenticated or isinstance(user, AnonymousUser):
        return False
    if user.is_superuser:
        scope = resolve_admin_scope(request)
        if scope.platform_admin:
            return True
        return scope.tenant_id is not None
    if not user.is_staff:
        return False
    allowed = get_allowed_tenant_ids(request)
    return bool(allowed)


def get_object_tenant_id(obj, tenant_field: str = "tenant") -> int | None:
    if obj is None:
        return None
    if tenant_field == "tenant":
        return getattr(obj, "tenant_id", None)
    parts = tenant_field.split("__")
    value = obj
    for part in parts:
        if value is None:
            return None
        value = getattr(value, part, None)
    return value if isinstance(value, int) else getattr(value, "pk", value)
