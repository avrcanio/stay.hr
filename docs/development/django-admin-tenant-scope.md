# Django admin — tenant scope

Guidance for tenant-scoped models in Django admin (`/admin/` on platform or tenant domains).

## Which mixin to use

| Situation | Use |
|-----------|-----|
| Model has `tenant` FK (or `TenantScopedModel`) | **`TenantScopedAdminMixin`** |
| Platform-only module (Tenant, TenantDomain, billing, …) | **`SuperuserOnlyAdminMixin`** |
| Global reference data (tourist tax ordinances, …) | Plain **`ModelAdmin`** |

`TenantHostScopedAdminMixin` is a **backward-compatible alias** for `TenantScopedAdminMixin` — same behaviour.

## What `TenantScopedAdminMixin` does

On **tenant domains** (e.g. `booking.uzorita.hr`):

- **Add form:** `tenant` field hidden; set automatically from host before save.
- **Change form:** `tenant` shown as **readonly**.
- **Save:** `apply_host_tenant()` always overwrites `tenant_id` from host — POST tampering is ignored.
- **Querysets:** changelist and FK widgets filtered to allowed tenants.

On **platform admin** (`admin.stay.hr`):

- Superusers: full multi-tenant access; `tenant` editable (raw id by default).
- Staff: only tenants where they have `TenantMembership`.

Scope resolution lives in [`backend/apps/tenants/admin_scope.py`](../../backend/apps/tenants/admin_scope.py). Admins should **not** call `resolve_admin_scope()` directly — use `admin.host_tenant_id(request)` etc.

## Forms

When the model has a `tenant` FK and you use a custom `ModelForm`, inherit **`TenantHostScopedModelForm`** ([`backend/apps/core/admin_forms.py`](../../backend/apps/core/admin_forms.py)).

The admin mixin injects `host_tenant_id` via `get_form()`. The form sets `instance.tenant_id` before validation — **no HTTP request in `clean()`**.

```python
from apps.core.admin_forms import TenantHostScopedModelForm

class MyAdminForm(TenantHostScopedModelForm):
    class Meta:
        model = MyModel
        fields = ("tenant", "property", "name")
```

## FK widgets: dropdown vs raw id

Do **not** use a static `raw_id_fields` attribute on tenant-scoped admins.

Configure per admin:

```python
class MyAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    platform_raw_id_fields = ("tenant", "reservation", "uploaded_by")
    # property / property_obj are dropdowns via host_dropdown_fk_fields (mixin default)
```

| Class attribute | Purpose |
|-----------------|--------|
| `platform_raw_id_fields` | Raw id widgets on **platform** host only |
| `host_dropdown_fk_fields` | Always `<select>` (default: `property`, `property_obj`) |
| `host_hidden_fields` | Hidden on add when host-scoped (default: `tenant`) |
| `host_readonly_fields` | Readonly on change (default: `tenant`) |

Use **raw id** only for high-cardinality FKs (reservations, users). Use **dropdown** for properties and other short lists.

## Custom save paths

If `save_model()` does not call `super().save_model()` on add (e.g. CSV import), call **`self.apply_host_tenant(request, obj)`** at the start — same authority as the mixin save path.

Example: [`BookingPayoutImportAdmin`](../../backend/apps/reservations/booking_payout_admin.py).

## Tests

When changing admin scope behaviour, run:

```bash
./scripts/run-tests-postgis.sh \
  apps.tenants.tests.test_admin_tenant_scope \
  apps.reservations.tests.test_booking_payout_admin_tenant_scope \
  -v 2
```

Include a **POST tampering** test when adding new host-scoped import/upload admins: submit wrong `tenant_id`, assert backend uses host tenant.

## Related docs

- [booking-payout-admin-ux-plan.md](booking-payout-admin-ux-plan.md) — original design for payout import admin
- [README.md — Admin on tenant domains](../../README.md)
