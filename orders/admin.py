from django.contrib import admin

from orders.models import Order, OrderItem, OrderStatusHistory, PrintJob


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("menu_item", "quantity", "unit_price")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "total", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("customer__username",)
    inlines = (OrderItemInline,)
    readonly_fields = ("customer", "status", "total", "created_at", "updated_at", "collected_at")


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "old_status", "new_status", "actor", "changed_at")
    readonly_fields = ("order", "old_status", "new_status", "actor", "changed_at")


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = ("order", "kind", "status", "retry_count", "updated_at")
    readonly_fields = ("order", "kind", "status", "retry_count", "last_error", "created_at", "updated_at", "printed_at")
