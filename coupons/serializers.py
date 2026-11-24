from rest_framework import serializers

from coupons.models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    redeemed_by_username = serializers.CharField(source="redeemed_by.username", read_only=True, allow_null=True)

    class Meta:
        model = Coupon
        fields = ("id", "order", "code", "expires_at", "is_redeemed", "redeemed_by", "redeemed_by_username", "redeemed_at")
        read_only_fields = fields


class CouponRedeemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32, trim_whitespace=True)
