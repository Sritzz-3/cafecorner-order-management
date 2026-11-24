from decimal import Decimal

from rest_framework import serializers

from menu.models import Category, MenuItem


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "display_order")


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    price = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = MenuItem
        fields = ("id", "category", "category_name", "name", "description", "price", "is_available")


class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ("is_available",)
