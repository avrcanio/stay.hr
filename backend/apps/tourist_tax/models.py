from django.db import models


class TouristTaxOrdinance(models.Model):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    issuer = models.CharField(max_length=255)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class TouristTaxZone(models.Model):
    class Kind(models.TextChoices):
        CENTRAL = "central", "Uže gradsko jezgro / turistička naselja"
        PERIPHERAL = "peripheral", "Okolna naselja (zaleđe)"

    ordinance = models.ForeignKey(
        TouristTaxOrdinance,
        on_delete=models.CASCADE,
        related_name="zones",
    )
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    settlements = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordinance_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["ordinance", "code"],
                name="tourist_tax_zone_unique_ordinance_code",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TouristTaxSeason(models.Model):
    class Kind(models.TextChoices):
        MAIN = "main", "Glavna sezona"
        OFF = "off", "Izvan sezone"

    ordinance = models.ForeignKey(
        TouristTaxOrdinance,
        on_delete=models.CASCADE,
        related_name="seasons",
    )
    code = models.SlugField(max_length=64)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    start_month = models.PositiveSmallIntegerField()
    start_day = models.PositiveSmallIntegerField()
    end_month = models.PositiveSmallIntegerField()
    end_day = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordinance_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["ordinance", "code"],
                name="tourist_tax_season_unique_ordinance_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ordinance.code} — {self.get_kind_display()}"


class TouristTaxAccommodationCategory(models.Model):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "tourist tax accommodation categories"

    def __str__(self) -> str:
        return self.name


class TouristTaxRate(models.Model):
    zone = models.ForeignKey(
        TouristTaxZone,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    season = models.ForeignKey(
        TouristTaxSeason,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    category = models.ForeignKey(
        TouristTaxAccommodationCategory,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["zone_id", "season_id", "category_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["zone", "season", "category"],
                name="tourist_tax_rate_unique_zone_season_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.zone.code} / {self.season.code} / {self.category.code}: {self.amount}"


class TouristTaxAgeBracket(models.Model):
    ordinance = models.ForeignKey(
        TouristTaxOrdinance,
        on_delete=models.CASCADE,
        related_name="age_brackets",
    )
    code = models.SlugField(max_length=64)
    min_age = models.PositiveSmallIntegerField()
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    multiplier = models.DecimalField(max_digits=4, decimal_places=2)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordinance_id", "sort_order", "min_age"]
        constraints = [
            models.UniqueConstraint(
                fields=["ordinance", "code"],
                name="tourist_tax_age_bracket_unique_ordinance_code",
            ),
        ]

    def __str__(self) -> str:
        max_label = str(self.max_age) if self.max_age is not None else "∞"
        return f"{self.code} ({self.min_age}–{max_label}): ×{self.multiplier}"
