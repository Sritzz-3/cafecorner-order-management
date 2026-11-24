from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from coupons.models import Coupon
from orders.models import PrintJob


class CouponRedemptionError(ValueError):
    status_code = 400
    detail = "Coupon could not be redeemed."


class CouponNotFound(CouponRedemptionError):
    status_code = 404
    detail = "Coupon code is invalid."


class CouponAlreadyUsed(CouponRedemptionError):
    status_code = 409
    detail = "Coupon has already been redeemed."


class CouponExpired(CouponRedemptionError):
    status_code = 410
    detail = "Coupon has expired."


@transaction.atomic
def issue_coupon_for_order(order):
    now = timezone.now()
    validity_days = settings.COUPON_VALIDITY_DAYS
    coupon = Coupon.objects.create(
        order=order,
        code=Coupon.generate_code(),
        expires_at=now + timedelta(days=validity_days),
    )
    PrintJob.objects.create(order=order, kind=PrintJob.Kind.COUPON_SLIP)
    return coupon


@transaction.atomic
def redeem_coupon(code, staff_user):
    normalized_code = code.strip().upper()
    now = timezone.now()
    changed = Coupon.objects.filter(
        code=normalized_code,
        is_redeemed=False,
        expires_at__gt=now,
    ).update(is_redeemed=True, redeemed_by=staff_user, redeemed_at=now)
    if changed == 1:
        return Coupon.objects.select_related("order", "redeemed_by").get(code=normalized_code)

    coupon = Coupon.objects.filter(code=normalized_code).first()
    if coupon is None:
        raise CouponNotFound(CouponNotFound.detail)
    if coupon.is_redeemed:
        raise CouponAlreadyUsed(CouponAlreadyUsed.detail)
    if coupon.expires_at <= now:
        raise CouponExpired(CouponExpired.detail)
    raise CouponRedemptionError()
