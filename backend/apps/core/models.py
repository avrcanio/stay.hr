from django.db import models


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantScopedManager(models.Manager.from_queryset(TenantQuerySet)):
    pass


class TenantScopedModel(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        db_index=True,
    )

    objects = TenantScopedManager()

    class Meta:
        abstract = True
