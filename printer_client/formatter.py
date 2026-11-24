from datetime import datetime
from decimal import Decimal
import textwrap


def _safe_text(value):
    return "".join(character if character.isprintable() else " " for character in str(value))


def _check_width(width):
    if width not in (32, 42):
        raise ValueError("Receipt width must be 32 or 42 characters.")


def _time_label(value):
    if not value:
        return "Unknown time"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return _safe_text(value)


def _amount(value):
    return f"{Decimal(str(value)):.2f}"


def _item_lines(item, width):
    quantity = int(item["quantity"])
    name = _safe_text(item.get("item_name") or item.get("name") or "Item")
    line_total = item.get("line_total")
    if line_total is None:
        line_total = Decimal(str(item["unit_price"])) * quantity
    right = _amount(line_total)
    left_width = max(8, width - len(right) - 1)
    wrapped = textwrap.wrap(f"{quantity} x {name}", width=left_width) or [f"{quantity} x"]
    wrapped[-1] = wrapped[-1].ljust(width - len(right)) + right
    return [line[:width] for line in wrapped]


def format_order_slip(job, width=42):
    _check_width(width)
    order = job["order"]
    divider = "-" * width
    lines = ["CAFE CORNER".center(width), f"ORDER #{order['id']}".center(width), f"Time: {_time_label(order.get('created_at'))}", divider]
    for item in order.get("items", []):
        lines.extend(_item_lines(item, width))
    lines.extend((divider, f"TOTAL {('₹' + _amount(order['total'])):>{width - 6}}"))
    return "\n".join(lines) + "\n"


def format_coupon_slip(job, width=42):
    _check_width(width)
    order = job["order"]
    divider = "-" * width
    lines = [
        "CAFE CORNER".center(width),
        "REWARD COUPON".center(width),
        f"Order #{order['id']}",
        divider,
        "Your next visit reward:",
        _safe_text(job["coupon_code"]).center(width),
        f"Expires: {_time_label(job.get('coupon_expires_at'))}",
        divider,
    ]
    return "\n".join(line[:width] for line in lines) + "\n"
