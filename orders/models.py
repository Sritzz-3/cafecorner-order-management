from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "PLACED", "Placed"
        PREPARING = "PREPARING", "Preparing"
        READY = "READY", "Ready"
        COLLECTED = "COLLECTED", "Collected"
        CANCELLED = "CANCELLED", "Cancelled"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLACED)
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    ALLOWED_TRANSITIONS = {
        Status.PLACED: (Status.PREPARING, Status.CANCELLED),
        Status.PREPARING: (Status.READY,),
        Status.READY: (Status.COLLECTED,),
        Status.COLLECTED: (),
        Status.CANCELLED: (),
    }

    class Meta:
        ordering = ("created_at", "pk")

    def transition_to(self, new_status, actor, expected_status=None):
        """Conditionally apply a transition so stale staff actions cannot overwrite newer state."""
        from orders.services import InvalidOrderTransition, StaleOrderStatus

        expected = expected_status or self.status
        if new_status not in self.ALLOWED_TRANSITIONS[expected]:
            raise InvalidOrderTransition(f"Cannot move an order from {expected} to {new_status}.")
        with transaction.atomic():
            now = timezone.now()
            changed = Order.objects.filter(pk=self.pk, status=expected).update(status=new_status, updated_at=now)
            if changed != 1:
                raise StaleOrderStatus("This order changed before your update. Refresh the queue and try again.")
            OrderStatusHistory.objects.create(
                order_id=self.pk,
                old_status=expected,
                new_status=new_status,
                actor=actor,
            )
            self.status = new_status
            self.updated_at = now
            return self

    def advance(self, actor, expected_status=None):
        """Move to the next forward state; cancellation stays a customer action."""
        expected = expected_status or self.status
        forward_status = next(
            (status for status in self.ALLOWED_TRANSITIONS[expected] if status != self.Status.CANCELLED),
            None,
        )
        if forward_status is None:
            from orders.services import InvalidOrderTransition

            raise InvalidOrderTransition(f"Order in {expected} cannot advance further.")
        return self.transition_to(forward_status, actor, expected_status=expected)

    def __str__(self):
        return f"Order #{self.pk} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey("menu.MenuItem", on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(20)])
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])

    class Meta:
        ordering = ("pk",)

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} × {self.menu_item.name}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    old_status = models.CharField(max_length=12, choices=Order.Status.choices, blank=True)
    new_status = models.CharField(max_length=12, choices=Order.Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="order_status_changes")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("changed_at", "pk")


class PrintJob(models.Model):
    class Kind(models.TextChoices):
        ORDER_SLIP = "ORDER_SLIP", "Order slip"
        COUPON_SLIP = "COUPON_SLIP", "Coupon slip"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PRINTED = "PRINTED", "Printed"
        FAILED = "FAILED", "Failed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="print_jobs")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    retry_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    printed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [models.UniqueConstraint(fields=("order", "kind"), name="unique_print_job_kind_per_order")]

    def __str__(self):
        return f"{self.get_kind_display()} for order #{self.order_id}"
