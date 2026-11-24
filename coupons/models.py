import secrets

from django.conf import settings
from django.db import models


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 24


class Coupon(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="coupon")
    code = models.CharField(max_length=CODE_LENGTH, unique=True)
    expires_at = models.DateTimeField()
    is_redeemed = models.BooleanField(default=False)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redeemed_coupons",
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    @classmethod
    def generate_code(cls):
        while True:
            candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if not cls.objects.filter(code=candidate).exists():
                return candidate

    def __str__(self):
        return self.code
