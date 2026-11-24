from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Profile
from menu.models import Category, MenuItem
from orders.models import Order, OrderItem, OrderStatusHistory, PrintJob
from orders.services import InvalidOrderRequest, InvalidOrderTransition, StaleOrderStatus, place_order


class OrderServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="customer", password="safe-pass-123")
        self.staff = User.objects.create_user(username="staff", password="safe-pass-123")
        self.staff.profile.role = Profile.Role.STAFF
        self.staff.profile.save()
        self.category = Category.objects.create(name="Drinks")
        self.coffee = MenuItem.objects.create(category=self.category, name="Latte", price=Decimal("4.25"))
        self.tea = MenuItem.objects.create(category=self.category, name="Tea", price=Decimal("2.00"))

    def test_total_is_calculated_from_current_server_prices_and_slip_is_queued(self):
        order = place_order(
            self.customer,
            [{"menu_item_id": self.coffee.pk, "quantity": 2}, {"menu_item_id": self.tea.pk, "quantity": 1}],
        )

        self.assertEqual(order.total, Decimal("10.50"))
        self.assertEqual(list(order.items.values_list("unit_price", flat=True)), [Decimal("4.25"), Decimal("2.00")])
        self.assertTrue(order.print_jobs.filter(kind=PrintJob.Kind.ORDER_SLIP, status=PrintJob.Status.PENDING).exists())
        initial = order.history.get()
        self.assertEqual((initial.old_status, initial.new_status, initial.actor), ("", Order.Status.PLACED, self.customer))

    def test_menu_price_change_does_not_change_existing_order_snapshot(self):
        order = place_order(self.customer, [{"menu_item_id": self.coffee.pk, "quantity": 2}])
        self.coffee.price = Decimal("7.00")
        self.coffee.save(update_fields=("price",))

        line = order.items.get()
        self.assertEqual(line.unit_price, Decimal("4.25"))
        self.assertEqual(line.line_total, Decimal("8.50"))
        self.assertEqual(order.total, Decimal("8.50"))

    def test_empty_duplicate_invalid_quantity_and_unavailable_lines_are_rejected(self):
        invalid_inputs = (
            [],
            [{"menu_item_id": self.coffee.pk, "quantity": 0}],
            [{"menu_item_id": self.coffee.pk, "quantity": -1}],
            [{"menu_item_id": self.coffee.pk, "quantity": 21}],
            [
                {"menu_item_id": self.coffee.pk, "quantity": 1},
                {"menu_item_id": self.coffee.pk, "quantity": 2},
            ],
        )
        for lines in invalid_inputs:
            with self.subTest(lines=lines), self.assertRaises(InvalidOrderRequest):
                place_order(self.customer, lines)

        self.tea.is_available = False
        self.tea.save(update_fields=("is_available",))
        with self.assertRaises(InvalidOrderRequest):
            place_order(
                self.customer,
                [
                    {"menu_item_id": self.coffee.pk, "quantity": 1},
                    {"menu_item_id": self.tea.pk, "quantity": 1},
                ],
            )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(PrintJob.objects.count(), 0)

    def test_print_job_failure_rolls_back_order_items_and_history(self):
        with patch("orders.services.PrintJob.objects.create", side_effect=RuntimeError("print queue unavailable")):
            with self.assertRaises(RuntimeError):
                place_order(self.customer, [{"menu_item_id": self.coffee.pk, "quantity": 1}])

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(OrderStatusHistory.objects.count(), 0)
        self.assertEqual(PrintJob.objects.count(), 0)

    def test_each_allowed_transition_writes_history_with_actor(self):
        order = place_order(self.customer, [{"menu_item_id": self.coffee.pk, "quantity": 1}])

        order.transition_to(Order.Status.PREPARING, self.staff)
        order.transition_to(Order.Status.READY, self.staff)
        order.transition_to(Order.Status.COLLECTED, self.staff)

        rows = list(order.history.values_list("old_status", "new_status", "actor_id"))
        self.assertEqual(
            rows,
            [
                ("", Order.Status.PLACED, self.customer.pk),
                (Order.Status.PLACED, Order.Status.PREPARING, self.staff.pk),
                (Order.Status.PREPARING, Order.Status.READY, self.staff.pk),
                (Order.Status.READY, Order.Status.COLLECTED, self.staff.pk),
            ],
        )

    def test_customer_cancellation_is_the_only_alternate_valid_transition(self):
        order = place_order(self.customer, [{"menu_item_id": self.coffee.pk, "quantity": 1}])

        order.transition_to(Order.Status.CANCELLED, self.customer)

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.history.last().new_status, Order.Status.CANCELLED)

    def test_stale_expected_status_cannot_create_a_duplicate_transition(self):
        order = place_order(self.customer, [{"menu_item_id": self.coffee.pk, "quantity": 1}])
        stale_read = Order.objects.get(pk=order.pk)
        order.advance(self.staff)

        with self.assertRaises(StaleOrderStatus):
            stale_read.advance(self.staff)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)
        self.assertEqual(order.history.count(), 2)

    def test_every_invalid_transition_is_rejected_without_history_rows(self):
        path_to_status = {
            Order.Status.PLACED: (),
            Order.Status.PREPARING: (Order.Status.PREPARING,),
            Order.Status.READY: (Order.Status.PREPARING, Order.Status.READY),
            Order.Status.COLLECTED: (Order.Status.PREPARING, Order.Status.READY, Order.Status.COLLECTED),
            Order.Status.CANCELLED: (Order.Status.CANCELLED,),
        }
        for start, path in path_to_status.items():
            for target in Order.Status.values:
                if target in Order.ALLOWED_TRANSITIONS[start]:
                    continue
                with self.subTest(start=start, target=target):
                    order = place_order(self.customer, [{"menu_item_id": self.coffee.pk, "quantity": 1}])
                    for state in path:
                        actor = self.customer if state == Order.Status.CANCELLED else self.staff
                        order.transition_to(state, actor)
                    history_count = order.history.count()
                    with self.assertRaises(InvalidOrderTransition):
                        order.transition_to(target, self.staff)
                    self.assertEqual(order.history.count(), history_count)


class OrderApiTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="customer", password="safe-pass-123")
        self.other_customer = User.objects.create_user(username="other", password="safe-pass-123")
        self.staff = User.objects.create_user(username="staff", password="safe-pass-123")
        self.staff.profile.role = Profile.Role.STAFF
        self.staff.profile.save()
        self.admin = User.objects.create_user(username="manager", password="safe-pass-123")
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save()
        self.category = Category.objects.create(name="Coffee")
        self.item = MenuItem.objects.create(category=self.category, name="Mocha", price=Decimal("5.10"))

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def create_order(self, customer=None):
        return place_order(customer or self.customer, [{"menu_item_id": self.item.pk, "quantity": 1}])

    def test_client_supplied_price_and_total_are_ignored(self):
        client = self.client_for(self.customer)

        response = client.post(
            "/api/orders/",
            {
                "items": [{"menu_item_id": self.item.pk, "quantity": 2, "price": "0.01"}],
                "total": "0.01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["total"], "10.20")
        self.assertEqual(response.data["items"][0]["unit_price"], "5.10")

    def test_api_rejects_empty_duplicate_and_out_of_range_quantities(self):
        client = self.client_for(self.customer)
        payloads = (
            {"items": []},
            {"items": [{"menu_item_id": self.item.pk, "quantity": 0}]},
            {"items": [{"menu_item_id": self.item.pk, "quantity": 21}]},
            {
                "items": [
                    {"menu_item_id": self.item.pk, "quantity": 1},
                    {"menu_item_id": self.item.pk, "quantity": 2},
                ]
            },
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(client.post("/api/orders/", payload, format="json").status_code, 400)

    def test_customer_can_only_view_own_orders_and_cancel_only_while_placed(self):
        own = self.create_order()
        other = self.create_order(self.other_customer)
        client = self.client_for(self.customer)

        mine = client.get("/api/orders/mine/")
        foreign_detail = client.get(f"/api/orders/{other.pk}/")
        queue = client.get("/api/orders/queue/")
        advance = client.post(f"/api/orders/{own.pk}/advance/")
        cancel = client.post(f"/api/orders/{own.pk}/cancel/")
        history = client.get(f"/api/orders/{own.pk}/history/")

        self.assertEqual([row["id"] for row in mine.data["results"]], [own.pk])
        self.assertEqual(foreign_detail.status_code, 404)
        self.assertEqual(queue.status_code, 403)
        self.assertEqual(advance.status_code, 403)
        self.assertEqual(history.status_code, 403)
        self.assertEqual(cancel.status_code, 200)
        own.refresh_from_db()
        self.assertEqual(own.status, Order.Status.CANCELLED)
        self.assertEqual(client.post(f"/api/orders/{other.pk}/cancel/").status_code, 404)

    def test_customer_cannot_cancel_after_order_is_in_preparation(self):
        order = self.create_order()
        order.transition_to(Order.Status.PREPARING, self.staff)

        response = self.client_for(self.customer).post(f"/api/orders/{order.pk}/cancel/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(order.history.count(), 2)

    def test_stale_staff_advance_returns_409_without_an_extra_history_row(self):
        order = self.create_order()
        stale_read = Order.objects.get(pk=order.pk)
        order.advance(self.staff)

        with patch("orders.api.OrderViewSet.get_object", return_value=stale_read):
            response = self.client_for(self.staff).post(f"/api/orders/{order.pk}/advance/")

        self.assertEqual(response.status_code, 409)
        self.assertIn("changed before your update", response.data["detail"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)
        self.assertEqual(order.history.count(), 2)

    def test_staff_can_see_queue_and_advance_but_not_cancel_or_read_history(self):
        order = self.create_order()
        other_order = self.create_order(self.other_customer)
        client = self.client_for(self.staff)

        queue = client.get("/api/orders/queue/")
        all_orders = client.get("/api/orders/")
        advance = client.post(f"/api/orders/{order.pk}/advance/")
        cancel = client.post(f"/api/orders/{order.pk}/cancel/")
        history = client.get(f"/api/orders/{order.pk}/history/")

        self.assertEqual([row["id"] for row in queue.data["results"]], [order.pk, other_order.pk])
        self.assertEqual([row["id"] for row in all_orders.data["results"]], [order.pk, other_order.pk])
        self.assertEqual(advance.status_code, 200)
        self.assertEqual(advance.data["status"], Order.Status.PREPARING)
        self.assertEqual(cancel.status_code, 403)
        self.assertEqual(history.status_code, 403)
        self.assertEqual(
            client.post("/api/orders/", {"items": [{"menu_item_id": self.item.pk, "quantity": 1}]}, format="json").status_code,
            403,
        )

    def test_admin_can_advance_and_view_history(self):
        order = self.create_order()
        client = self.client_for(self.admin)

        queue = client.get("/api/orders/queue/")
        advance = client.post(f"/api/orders/{order.pk}/advance/")
        history = client.get(f"/api/orders/{order.pk}/history/")

        self.assertEqual([row["id"] for row in queue.data["results"]], [order.pk])
        self.assertEqual(advance.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data[-1]["new_status"], Order.Status.PREPARING)

    def test_polling_since_filters_mine_and_staff_queue(self):
        older = self.create_order()
        newer = self.create_order()
        threshold = timezone.now() - timedelta(seconds=30)
        Order.objects.filter(pk=older.pk).update(updated_at=threshold - timedelta(seconds=10))
        since = urlencode({"since": threshold.isoformat()})

        mine = self.client_for(self.customer).get(f"/api/orders/mine/?{since}")
        queue = self.client_for(self.staff).get(f"/api/orders/queue/?{since}")
        self.assertEqual([row["id"] for row in mine.data["results"]], [newer.pk])
        self.assertEqual([row["id"] for row in queue.data["results"]], [newer.pk])

    def test_updated_old_order_appears_in_polling_after_status_advance(self):
        order = self.create_order()
        old_updated_at = order.updated_at
        since = urlencode({"since": (old_updated_at + timedelta(microseconds=1)).isoformat()})

        order.advance(self.staff)
        order.refresh_from_db()
        mine = self.client_for(self.customer).get(f"/api/orders/mine/?{since}")
        queue = self.client_for(self.staff).get(f"/api/orders/queue/?{since}")

        self.assertGreater(order.updated_at, old_updated_at)
        self.assertEqual([row["id"] for row in mine.data["results"]], [order.pk])
        self.assertEqual([row["id"] for row in queue.data["results"]], [order.pk])

    def test_queue_is_oldest_first_and_hides_completed_orders(self):
        older = self.create_order()
        newer = self.create_order()
        completed = self.create_order()
        completed.transition_to(Order.Status.PREPARING, self.staff)
        completed.transition_to(Order.Status.READY, self.staff)
        completed.transition_to(Order.Status.COLLECTED, self.staff)

        response = self.client_for(self.staff).get("/api/orders/queue/")

        self.assertEqual([row["id"] for row in response.data["results"]], [older.pk, newer.pk])

    def test_invalid_since_timestamp_returns_400(self):
        response = self.client_for(self.customer).get("/api/orders/mine/?since=not-a-date")

        self.assertEqual(response.status_code, 400)
        self.assertIn("since", response.data)

    def test_order_list_and_polling_queries_do_not_grow_with_order_count(self):
        second = MenuItem.objects.create(category=self.category, name="Espresso", price=Decimal("2.00"))
        first_order = self.create_order()
        place_order(
            self.customer,
            [{"menu_item_id": self.item.pk, "quantity": 1}, {"menu_item_id": second.pk, "quantity": 1}],
        )
        third_order = self.create_order()
        staff_client = self.client_for(self.staff)
        customer_client = self.client_for(self.customer)

        def measured_get(client, path):
            with CaptureQueriesContext(connection) as queries:
                response = client.get(path)
            self.assertEqual(response.status_code, 200)
            return response, len(queries)

        detailed_three, list_queries_three = measured_get(staff_client, "/api/orders/")
        mine_three, mine_queries_three = measured_get(customer_client, "/api/orders/mine/")
        queue_three, queue_queries_three = measured_get(staff_client, "/api/orders/queue/")

        for _ in range(12):
            self.create_order()

        detailed_fifteen, list_queries_fifteen = measured_get(staff_client, "/api/orders/")
        mine_fifteen, mine_queries_fifteen = measured_get(customer_client, "/api/orders/mine/")
        queue_fifteen, queue_queries_fifteen = measured_get(staff_client, "/api/orders/queue/")

        self.assertEqual(list_queries_three, list_queries_fifteen)
        self.assertEqual(mine_queries_three, mine_queries_fifteen)
        self.assertEqual(queue_queries_three, queue_queries_fifteen)
        self.assertEqual(len(detailed_three.data["results"]), 3)
        self.assertEqual(len(detailed_fifteen.data["results"]), 15)
        self.assertEqual(len(mine_three.data["results"]), 3)
        self.assertEqual(len(mine_fifteen.data["results"]), 15)
        self.assertEqual(len(queue_three.data["results"]), 3)
        self.assertEqual(len(queue_fifteen.data["results"]), 15)
        self.assertEqual(detailed_three.data["results"][0]["items"][0]["item_name"], "Mocha")
        self.assertEqual(first_order.items.count(), 1)
        self.assertIsNotNone(third_order.pk)


class OrderPageTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="page-customer", password="safe-pass-123")
        self.staff = User.objects.create_user(username="page-staff", password="safe-pass-123")
        self.staff.profile.role = Profile.Role.STAFF
        self.staff.profile.save()
        self.admin = User.objects.create_user(username="page-manager", password="safe-pass-123")
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save()
        self.category = Category.objects.create(name="Cafe drinks")
        self.item = MenuItem.objects.create(category=self.category, name="Cappuccino", price=Decimal("4.75"))

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def make_order(self, quantity=1):
        return place_order(self.customer, [{"menu_item_id": self.item.pk, "quantity": quantity}])

    def test_customer_cart_and_order_pages_are_role_protected(self):
        order = self.make_order()
        customer_client = self.client_for(self.customer)
        self.assertEqual(customer_client.get("/orders/cart/").status_code, 200)
        mine = customer_client.get("/orders/mine/")
        self.assertEqual(mine.status_code, 200)
        self.assertContains(mine, f"Order #{order.pk}")
        self.assertContains(mine, "live_orders.js")

        self.assertEqual(self.client_for(self.staff).get("/orders/cart/").status_code, 403)
        self.assertEqual(self.client_for(self.admin).get("/orders/mine/").status_code, 403)

    def test_staff_queue_page_displays_active_orders_and_is_staff_only(self):
        self.make_order()

        response = self.client_for(self.staff).get("/orders/queue/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cappuccino")
        self.assertContains(response, "staff_queue.js")
        self.assertEqual(self.client_for(self.customer).get("/orders/queue/").status_code, 403)

    def test_admin_dashboard_aggregates_orders_and_collected_revenue(self):
        collected = self.make_order(quantity=2)
        collected.transition_to(Order.Status.PREPARING, self.staff)
        collected.transition_to(Order.Status.READY, self.staff)
        collected.transition_to(Order.Status.COLLECTED, self.staff)
        self.make_order(quantity=1)
        yesterday = self.make_order(quantity=5)
        yesterday.transition_to(Order.Status.PREPARING, self.staff)
        yesterday.transition_to(Order.Status.READY, self.staff)
        yesterday.transition_to(Order.Status.COLLECTED, self.staff)
        Order.objects.filter(pk=yesterday.pk).update(created_at=timezone.now() - timedelta(days=1))

        response = self.client_for(self.admin).get("/orders/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["orders_today"], 2)
        self.assertEqual(response.context["revenue_today"], Decimal("9.50"))
        self.assertEqual(response.context["revenue_rule"], "Revenue includes only orders collected today.")
        self.assertEqual(response.context["top_items"][0]["quantity_sold"], 2)
        self.assertEqual(response.context["top_items"][0]["revenue"], Decimal("9.50"))
        self.assertContains(response, "Revenue includes only orders collected today.")
        self.assertEqual(self.client_for(self.staff).get("/orders/dashboard/").status_code, 403)
