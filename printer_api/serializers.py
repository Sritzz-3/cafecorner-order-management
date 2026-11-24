from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from orders.models import Order, OrderItem, PrintJob


class PrintOrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="menu_item.name", read_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ("item_name", "quantity", "unit_price", "line_total")


class PrintOrderSerializer(serializers.ModelSerializer):
    items = PrintOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ("id", "status", "created_at", "total", "items")


class PrintJobSerializer(serializers.ModelSerializer):
    order = PrintOrderSerializer(read_only=True)
    coupon_code = serializers.SerializerMethodField()
    coupon_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = PrintJob
        fields = ("id", "kind", "status", "retry_count", "last_error", "claimed_at", "printed_at", "order", "coupon_code", "coupon_expires_at")

    @extend_schema_field(OpenApiTypes.STR)
    def get_coupon_code(self, job):
        if job.kind == PrintJob.Kind.COUPON_SLIP:
            return job.order.coupon.code
        return None

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_coupon_expires_at(self, job):
        if job.kind == PrintJob.Kind.COUPON_SLIP:
            return job.order.coupon.expires_at
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.kind != PrintJob.Kind.COUPON_SLIP:
            data.pop("coupon_code", None)
            data.pop("coupon_expires_at", None)
        return data


class StaffPrintJobSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PrintJob
        fields = ("id", "order_id", "kind", "status", "retry_count", "last_error", "created_at", "updated_at")


class PendingLimitSerializer(serializers.Serializer):
    limit = serializers.IntegerField(required=False, default=10, min_value=1, max_value=100)


class PrintFailureSerializer(serializers.Serializer):
    error = serializers.CharField(max_length=5000, allow_blank=False, trim_whitespace=True)
