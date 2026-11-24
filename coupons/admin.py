from django.contrib import admin

from coupons.models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "order", "expires_at", "is_redeemed", "redeemed_by", "redeemed_at")
    list_filter = ("is_redeemed", "expires_at")
    search_fields = ("code", "order__customer__username")
    readonly_fields = ("order", "code", "expires_at", "is_redeemed", "redeemed_by", "redeemed_at", "created_at")
