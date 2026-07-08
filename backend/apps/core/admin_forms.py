"""Shared Django admin form helpers."""

from __future__ import annotations

from django import forms


class TenantHostScopedModelForm(forms.ModelForm):
    """
    Pre-set tenant from host scope before validation.

    Used with ``TenantScopedAdminMixin.get_form()`` which passes ``host_tenant_id``.
    Forms must not call ``resolve_admin_scope()`` or read the HTTP request.
    """

    def __init__(self, *args, host_tenant_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if host_tenant_id is not None and not self.instance.pk:
            self.instance.tenant_id = host_tenant_id
        if host_tenant_id is not None and "tenant" in self.fields:
            del self.fields["tenant"]
