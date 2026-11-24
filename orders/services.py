from decimal import Decimal

from django.db import transaction

from menu.models import MenuItem
from orders.models import Order, OrderItem, OrderStatusHistory, PrintJob


class InvalidOrderRequest(ValueError):
    pass


class InvalidOrderTransition(ValueError):
    pass


class StaleOrderStatus(ValueError):
    pass


MAX_QUANTITY_PER_LINE = 20


@transaction.atomic
def place_order(customer, lines):
    """Re-read current menu prices and availability before storing an order."""
    if not lines:
        raise InvalidOrderRequest("An order must contain at least one item.")

    item_ids = [line.get("menu_item_id") for line in lines]
    if len(item_ids) != len(set(item_ids)):
        raise InvalidOrderRequest("Each menu item may appear only once in an order.")

    priced_lines = []
    total = Decimal("0.00")
    for line in lines:
        quantity = line.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY_PER_LINE:
            raise InvalidOrderRequest(f"Quantity must be between 1 and {MAX_QUANTITY_PER_LINE}.")
        try:
            item = MenuItem.objects.select_for_update().get(pk=line.get("menu_item_id"))
        except (MenuItem.DoesNotExist, TypeError, ValueError):
            raise InvalidOrderRequest("One or more menu items do not exist.")
        if not item.is_available:
            raise InvalidOrderRequest(f"{item.name} is not currently available.")
        priced_lines.append((item, quantity, item.price))
        total += item.price * quantity

    order = Order.objects.create(customer=customer, total=total)
    OrderItem.objects.bulk_create(
        [OrderItem(order=order, menu_item=item, quantity=quantity, unit_price=price) for item, quantity, price in priced_lines]
    )
    OrderStatusHistory.objects.create(order=order, old_status="", new_status=Order.Status.PLACED, actor=customer)
    PrintJob.objects.create(order=order, kind=PrintJob.Kind.ORDER_SLIP)
    return order
