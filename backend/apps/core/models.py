from django.db import models


class TenantScopedModel(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        db_index=True,
    )

    class Meta:
        abstract = True
