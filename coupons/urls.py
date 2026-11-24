from rest_framework.routers import DefaultRouter

from coupons.api import CouponViewSet

router = DefaultRouter()
router.register("", CouponViewSet, basename="coupon")

urlpatterns = router.urls
