from decimal import Decimal
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone

from orders.models import Order, OrderItem


def require_role(*group_names):
    def decorate(view):
        @wraps(view)
        @login_required
        def checked_view(request, *args, **kwargs):
            allowed = request.user.is_superuser or request.user.groups.filter(name__in=group_names).exists()
            if not allowed:
                return HttpResponseForbidden("You do not have access to this page.")
            return view(request, *args, **kwargs)

        return checked_view

    return decorate


@require_role("Customer")
def cart_page(request):
    return render(request, "orders/cart.html")


@require_role("Customer")
def my_orders_page(request):
    orders = (
        Order.objects.filter(customer=request.user)
        .prefetch_related("items__menu_item")
        .order_by("-created_at", "-pk")
    )
    return render(request, "orders/mine.html", {"orders": orders})


@require_role("Staff", "Admin")
def staff_queue_page(request):
    orders = (
        Order.objects.filter(status__in=(Order.Status.PLACED, Order.Status.PREPARING, Order.Status.READY))
        .select_related("customer")
        .prefetch_related("items__menu_item")
        .order_by("created_at", "pk")
    )
    return render(request, "orders/queue.html", {"orders": orders})


@require_role("Admin")
def admin_dashboard(request):
    today = timezone.localdate()
    today_orders = Order.objects.filter(created_at__date=today)
    collected_today = Order.objects.filter(status=Order.Status.COLLECTED, collected_at__date=today)
    revenue_today = (
        collected_today.aggregate(total=Sum("total"))["total"]
        or Decimal("0.00")
    )
    top_items = (
        OrderItem.objects.filter(order__collected_at__date=today, order__status=Order.Status.COLLECTED)
        .values("menu_item_id", "menu_item__name")
        .annotate(
            quantity_sold=Sum("quantity"),
            revenue=Sum(
                ExpressionWrapper(
                    F("unit_price") * F("quantity"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            ),
        )
        .order_by("-quantity_sold", "menu_item__name")[:5]
    )
    return render(
        request,
        "orders/dashboard.html",
        {
            "orders_today": today_orders.count(),
            "today": today,
            "revenue_today": revenue_today,
            "revenue_rule": "Revenue includes only orders collected today.",
            "top_items": top_items,
        },
    )
