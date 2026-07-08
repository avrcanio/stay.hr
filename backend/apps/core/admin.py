"""Shared Django admin mixins."""

from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation
from apps.tenants.admin_scope import (
    AdminScope,
    get_allowed_tenant_ids,
    get_allowed_tenants,
    get_object_tenant_id,
    is_platform_admin,
    staff_has_tenant_membership,
    user_has_tenant_access,
)


class SuperuserOnlyAdminMixin:
    """Restrict admin module to platform superusers."""

    def has_module_permission(self, request):
        return is_platform_admin(request)

    def has_view_permission(self, request, obj=None):
        return is_platform_admin(request)

    def has_add_permission(self, request):
        return is_platform_admin(request)

    def has_change_permission(self, request, obj=None):
        return is_platform_admin(request)

    def has_delete_permission(self, request, obj=None):
        return is_platform_admin(request)


class TenantScopedAdminMixin:
    """
    Tenant-scoped Django admin: queryset filtering, permissions, and host-aware UX.

    On tenant domains (``booking.example.hr``) the mixin automatically:
    - hides ``tenant`` on add forms,
    - shows ``tenant`` as readonly on change forms,
    - sets ``obj.tenant_id`` from the host before save (backend is authoritative),
    - filters FK querysets to allowed tenants.

    On platform admin (``admin.stay.hr``) superusers retain full multi-tenant access;
    staff see only their memberships.

    Conventions for new admins:
    - Use ``platform_raw_id_fields`` + ``get_raw_id_fields()`` — not ``raw_id_fields``.
    - Put low-cardinality FKs in ``host_dropdown_fk_fields`` (dropdown, not raw id).
    - Use ``raw_id`` only for high-cardinality relations (reservations, users, …).
    - Pair with ``TenantHostScopedModelForm`` when the model has a ``tenant`` FK.
    """

    tenant_field = "tenant"
    host_hidden_fields: tuple[str, ...] = ("tenant",)
    host_readonly_fields: tuple[str, ...] = ("tenant",)
    host_dropdown_fk_fields: tuple[str, ...] = ("property", "property_obj")
    platform_raw_id_fields: tuple[str, ...] = ("tenant",)

    def admin_scope(self, request) -> AdminScope:
        from apps.tenants.admin_scope import resolve_admin_scope

        return resolve_admin_scope(request)

    def host_tenant_id(self, request) -> int | None:
        return self.admin_scope(request).tenant_id

    def is_host_scoped(self, request) -> bool:
        return self.host_tenant_id(request) is not None

    def _allowed_tenant_ids(self, request) -> list[int] | None:
        return get_allowed_tenant_ids(request)

    def _tenant_filter_kwargs(self, request) -> dict:
        allowed = self._allowed_tenant_ids(request)
        if allowed is None:
            return {}
        if not allowed:
            return {f"{self.tenant_field}__in": []}
        return {f"{self.tenant_field}__in": allowed}

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        filt = self._tenant_filter_kwargs(request)
        if filt:
            qs = qs.filter(**filt)
        return qs

    def _tenant_scoped_admin_access(self, request) -> bool:
        """Staff or superuser with access on this admin host (platform or tenant-scoped)."""
        return staff_has_tenant_membership(request)

    def has_module_permission(self, request):
        if is_platform_admin(request):
            return super().has_module_permission(request)
        return self._tenant_scoped_admin_access(request)

    def _object_tenant_allowed(self, request, obj) -> bool:
        if obj is None:
            return True
        tenant_id = get_object_tenant_id(obj, self.tenant_field)
        return user_has_tenant_access(request, tenant_id)

    def has_view_permission(self, request, obj=None):
        if is_platform_admin(request):
            return super().has_view_permission(request, obj)
        if not self._tenant_scoped_admin_access(request):
            return False
        if obj is None:
            return True
        return self._object_tenant_allowed(request, obj)

    def has_add_permission(self, request):
        if is_platform_admin(request):
            return super().has_add_permission(request)
        return self._tenant_scoped_admin_access(request)

    def has_change_permission(self, request, obj=None):
        if is_platform_admin(request):
            return super().has_change_permission(request, obj)
        if not self._tenant_scoped_admin_access(request):
            return False
        if obj is None:
            return True
        return self._object_tenant_allowed(request, obj)

    def has_delete_permission(self, request, obj=None):
        if is_platform_admin(request):
            return super().has_delete_permission(request, obj)
        if not self._tenant_scoped_admin_access(request):
            return False
        if obj is None:
            return True
        return self._object_tenant_allowed(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        allowed = self._allowed_tenant_ids(request)
        if allowed is not None:
            if db_field.name == "tenant":
                kwargs["queryset"] = get_allowed_tenants(request)
            elif db_field.name in ("property", "property_obj"):
                kwargs["queryset"] = Property.objects.filter(tenant_id__in=allowed)
            elif db_field.name == "unit":
                kwargs["queryset"] = Unit.objects.filter(tenant_id__in=allowed)
            elif db_field.name == "reservation":
                kwargs["queryset"] = Reservation.objects.filter(tenant_id__in=allowed)
            elif db_field.name == "guest":
                kwargs["queryset"] = Guest.objects.filter(tenant_id__in=allowed)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _apply_host_hidden_fields(self, request, obj, fields):
        fields = list(fields)
        if obj is None and self.is_host_scoped(request):
            hidden = set(self.host_hidden_fields)
            fields = [f for f in fields if f not in hidden]
        return fields

    def _filter_fieldsets_hidden_fields(self, fieldsets, hidden: set[str]):
        filtered = []
        for title, options in fieldsets:
            fields = options.get("fields")
            if fields is None:
                filtered.append((title, options))
                continue
            if isinstance(fields, (list, tuple)):
                new_fields = tuple(f for f in fields if f not in hidden)
            else:
                new_fields = fields
            if new_fields:
                filtered.append((title, {**options, "fields": new_fields}))
        return tuple(filtered)

    def get_fields(self, request, obj=None):
        return self._apply_host_hidden_fields(request, obj, super().get_fields(request, obj))

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None and self.is_host_scoped(request):
            return self._filter_fieldsets_hidden_fields(fieldsets, set(self.host_hidden_fields))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            for field_name in self.host_readonly_fields:
                if field_name not in readonly:
                    readonly.append(field_name)
        return readonly

    def get_raw_id_fields(self, request, obj=None):
        base = tuple(getattr(self, "platform_raw_id_fields", ()) or ())
        if self.is_host_scoped(request):
            base = tuple(f for f in base if f not in self.host_hidden_fields)
        dropdown = set(self.host_dropdown_fk_fields)
        return tuple(f for f in base if f not in dropdown)

    def get_form(self, request, obj=None, **kwargs):
        from apps.core.admin_forms import TenantHostScopedModelForm

        host_tid = self.host_tenant_id(request)
        base_form = super().get_form(request, obj, **kwargs)

        if not issubclass(base_form, TenantHostScopedModelForm):
            return base_form

        class HostScopedForm(base_form):
            def __init__(self, *args, **form_kwargs):
                form_kwargs["host_tenant_id"] = host_tid
                super().__init__(*args, **form_kwargs)

        HostScopedForm.__name__ = base_form.__name__
        return HostScopedForm

    def _resolve_tenant_id_for_save(self, request, obj) -> int | None:
        tenant_id = get_object_tenant_id(obj, self.tenant_field)
        if tenant_id is not None:
            return tenant_id
        if self.tenant_field == "tenant" and hasattr(obj, "tenant_id"):
            return obj.tenant_id
        allowed = self._allowed_tenant_ids(request)
        if allowed and len(allowed) == 1 and self.tenant_field == "tenant":
            return allowed[0]
        return tenant_id

    def apply_host_tenant(self, request, obj) -> None:
        """Set tenant from host context and verify access. Call before validation/save."""
        if self.tenant_field == "tenant":
            host_tid = self.host_tenant_id(request)
            if host_tid is not None:
                obj.tenant_id = host_tid
            elif not getattr(obj, "tenant_id", None):
                allowed = self._allowed_tenant_ids(request) or []
                if len(allowed) == 1:
                    obj.tenant_id = allowed[0]
        tenant_id = self._resolve_tenant_id_for_save(request, obj)
        if not user_has_tenant_access(request, tenant_id):
            raise PermissionDenied("Nemate pristup ovom tenantu.")

    def _enforce_tenant_on_save(self, request, obj) -> None:
        self.apply_host_tenant(request, obj)

    def save_model(self, request, obj, form, change):
        self.apply_host_tenant(request, obj)
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        allowed = self._allowed_tenant_ids(request)
        parent = form.instance
        parent_tenant_id = getattr(parent, "tenant_id", None)
        if allowed is not None:
            for inline_form in formset.forms:
                if inline_form.cleaned_data.get("DELETE"):
                    continue
                instance = inline_form.instance
                if not inline_form.has_changed() and not instance.pk:
                    continue
                if hasattr(instance, "tenant_id"):
                    if not instance.tenant_id and parent_tenant_id:
                        instance.tenant_id = parent_tenant_id
                    tid = instance.tenant_id
                    if tid and tid not in allowed:
                        raise PermissionDenied("Nemate pristup ovom tenantu.")
        super().save_formset(request, form, formset, change)


class TenantHostScopedAdminMixin(TenantScopedAdminMixin):
    """Backward-compatible alias — behaviour is now in ``TenantScopedAdminMixin``."""
