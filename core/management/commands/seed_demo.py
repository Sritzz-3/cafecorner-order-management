from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.authtoken.models import Token

from accounts.models import Profile
from menu.models import Category, MenuItem
from orders.models import Order
from orders.services import place_order


DEMO_PASSWORD = "DEMO-ONLY-not-a-real-password-123!"
DEMO_ACCOUNTS = {
    "cafecorner_demo_customer": ("customer", False, False),
    "cafecorner_demo_staff": ("staff", False, False),
    "cafecorner_demo_admin": ("admin", True, True),
    "cafecorner_demo_printer": ("printer", False, False),
}


class Command(BaseCommand):
    help = "Create repeatable CafeCorner demo accounts, menu items, and sample orders."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is available only when DEBUG=True.")

        with transaction.atomic():
            users = self._create_users()
            items = self._create_menu()
            orders_created = self._create_orders(users["customer"], users["staff"], items)
            printer_token, token_created = Token.objects.get_or_create(user=users["printer"])

        self.stdout.write(self.style.SUCCESS("CafeCorner demo data is ready."))
        for username, (role, _, _) in DEMO_ACCOUNTS.items():
            self.stdout.write(f"{role.title()}: username={username} password={DEMO_PASSWORD}")
        if token_created:
            self.stdout.write(f"Printer token (copy it now): PRINTER_TOKEN={printer_token.key}")
        else:
            self.stdout.write("Printer token already exists; it was not displayed again.")
        self.stdout.write(f"Sample orders created this run: {orders_created}")

    def _create_users(self):
        User = get_user_model()
        users = {}
        for username, (role, is_staff, is_superuser) in DEMO_ACCOUNTS.items():
            user, _ = User.objects.get_or_create(username=username)
            user.email = f"{username}@example.invalid"
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.set_password(DEMO_PASSWORD)
            user.save()
            profile = user.profile
            profile.role = {
                "customer": Profile.Role.CUSTOMER,
                "staff": Profile.Role.STAFF,
                "admin": Profile.Role.ADMIN,
                "printer": Profile.Role.PRINTER,
            }[role]
            profile.save()
            users[role] = user
        return users

    def _create_menu(self):
        menu = (
            ("Coffee & Tea", 1, "Filter Coffee", "Strong South Indian filter coffee", "45.00"),
            ("Coffee & Tea", 1, "Masala Chai", "Ginger and cardamom milk tea", "35.00"),
            ("Quick Bites", 2, "Masala Toast", "Toasted sandwich with spiced potato", "85.00"),
            ("Quick Bites", 2, "Paneer Puff", "Flaky pastry with paneer filling", "55.00"),
            ("Sweets", 3, "Gulab Jamun", "Two warm milk-solid dumplings", "60.00"),
        )
        items = {}
        for category_name, display_order, name, description, price in menu:
            category, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={"display_order": display_order},
            )
            item, _ = MenuItem.objects.get_or_create(
                category=category,
                name=name,
                defaults={
                    "description": description,
                    "price": Decimal(price),
                    "is_available": True,
                },
            )
            items[name] = item
        return items

    def _create_orders(self, customer, staff, items):
        # The whole seed runs atomically. Existing demo-customer orders mean this sample set
        # has already been created, even if the demo customer has since placed more orders.
        if Order.objects.filter(customer=customer).exists():
            return 0

        samples = (
            ("PLACED", "Filter Coffee"),
            ("PREPARING", "Masala Chai"),
            ("READY", "Masala Toast"),
            ("COLLECTED", "Paneer Puff"),
            ("CANCELLED", "Gulab Jamun"),
        )
        for target_status, item_name in samples:
            order = place_order(customer, [{"menu_item_id": items[item_name].pk, "quantity": 1}])
            if target_status == Order.Status.CANCELLED:
                order.transition_to(Order.Status.CANCELLED, customer)
                continue
            transitions = {
                Order.Status.PLACED: (),
                Order.Status.PREPARING: (Order.Status.PREPARING,),
                Order.Status.READY: (Order.Status.PREPARING, Order.Status.READY),
                Order.Status.COLLECTED: (
                    Order.Status.PREPARING,
                    Order.Status.READY,
                    Order.Status.COLLECTED,
                ),
            }[target_status]
            for next_status in transitions:
                order.transition_to(next_status, staff)
        return len(samples)
