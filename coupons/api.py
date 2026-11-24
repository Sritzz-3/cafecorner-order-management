from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from accounts.permissions import IsAdminRole, IsCustomer, IsStaffRole
from coupons.models import Coupon
from coupons.serializers import CouponRedeemSerializer, CouponSerializer
from coupons.services import CouponRedemptionError, redeem_coupon


STAFF_OR_ADMIN = IsStaffRole | IsAdminRole


class CouponViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Coupon.objects.none()
    serializer_class = CouponSerializer
    throttle_scope = "coupon_redeem"

    def get_permissions(self):
        permission = STAFF_OR_ADMIN if self.action == "redeem" else IsCustomer
        return [permission()]

    def get_throttles(self):
        return [ScopedRateThrottle()] if self.action == "redeem" else []

    def get_queryset(self):
        return Coupon.objects.filter(order__customer=self.request.user).select_related("order", "redeemed_by")

    @action(detail=False, methods=("post",), url_path="redeem")
    def redeem(self, request):
        serializer = CouponRedeemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            coupon = redeem_coupon(serializer.validated_data["code"], request.user)
        except CouponRedemptionError as exc:
            return Response({"detail": exc.detail}, status=exc.status_code)
        return Response(CouponSerializer(coupon).data, status=status.HTTP_200_OK)
