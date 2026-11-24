from rest_framework import serializers

from orders.models import Order, OrderItem, OrderStatusHistory
from orders.services import MAX_QUANTITY_PER_LINE


class OrderLineInputSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_QUANTITY_PER_LINE)


class OrderCreateSerializer(serializers.Serializer):
    items = OrderLineInputSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        ids = [line["menu_item_id"] for line in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each menu item may appear only once in an order.")
        return items


class OrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="menu_item.name", read_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "menu_item", "item_name", "quantity", "unit_price", "line_total")
        read_only_fields = fields


class OrderSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ("id", "status", "total", "created_at", "updated_at")
        read_only_fields = fields


class OrderDetailSerializer(serializers.ModelSerializer):
    customer_username = serializers.CharField(source="customer.username", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ("id", "customer_username", "status", "total", "created_at", "updated_at", "items")
        read_only_fields = fields


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, allow_null=True)

    class Meta:
        model = OrderStatusHistory
        fields = ("old_status", "new_status", "actor_username", "changed_at")
        read_only_fields = fields
