from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "name")
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ("category__display_order", "name")
        constraints = [models.UniqueConstraint(fields=("category", "name"), name="unique_item_name_per_category")]

    def __str__(self):
        return self.name
