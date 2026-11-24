from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Profile
from menu.models import Category, MenuItem


class MenuRoleTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", display_order=1)
        self.available = MenuItem.objects.create(
            category=self.category, name="Flat White", description="Double espresso with milk", price=Decimal("4.50")
        )
        self.unavailable = MenuItem.objects.create(
            category=self.category, name="Cold Brew", description="Slow steeped", price=Decimal("3.75"), is_available=False
        )
        self.customer = User.objects.create_user(username="customer", password="test-pass-123")
        self.staff = User.objects.create_user(username="staff", password="test-pass-123")
        self.staff.profile.role = Profile.Role.STAFF
        self.staff.profile.save()
        self.admin = User.objects.create_user(username="manager", password="test-pass-123")
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save()

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_customer_only_sees_available_menu_items_and_categories(self):
        client = self.client_for(self.customer)

        items = client.get("/api/menu/items/")
        categories = client.get("/api/menu/categories/")
        hidden_detail = client.get(f"/api/menu/items/{self.unavailable.pk}/")

        self.assertEqual(items.status_code, 200)
        self.assertEqual([row["name"] for row in items.data["results"]], ["Flat White"])
        self.assertEqual(categories.status_code, 200)
        self.assertEqual([row["name"] for row in categories.data["results"]], ["Coffee"])
        self.assertEqual(hidden_detail.status_code, 404)

    def test_customer_cannot_change_availability_or_manage_menu(self):
        client = self.client_for(self.customer)

        toggle = client.patch(f"/api/menu/items/{self.available.pk}/availability/", {"is_available": False}, format="json")
        edit = client.patch(f"/api/menu/items/{self.available.pk}/", {"name": "Changed"}, format="json")
        create_item = client.post(
            "/api/menu/items/",
            {"category": self.category.pk, "name": "Unauthorized", "price": "1.00"},
            format="json",
        )
        create_category = client.post("/api/menu/categories/", {"name": "Tea", "display_order": 2}, format="json")

        self.assertEqual(toggle.status_code, 403)
        self.assertEqual(edit.status_code, 403)
        self.assertEqual(create_item.status_code, 403)
        self.assertEqual(create_category.status_code, 403)
        self.available.refresh_from_db()
        self.assertTrue(self.available.is_available)

    def test_staff_can_toggle_availability_but_cannot_edit_menu(self):
        client = self.client_for(self.staff)

        toggle = client.patch(f"/api/menu/items/{self.available.pk}/availability/", {"is_available": False}, format="json")
        edit = client.patch(f"/api/menu/items/{self.available.pk}/", {"name": "Changed"}, format="json")
        create_category = client.post("/api/menu/categories/", {"name": "Tea", "display_order": 2}, format="json")

        self.assertEqual(toggle.status_code, 200)
        self.assertFalse(toggle.data["is_available"])
        staff_items = client.get("/api/menu/items/")
        self.assertEqual(staff_items.status_code, 200)
        self.assertEqual(len(staff_items.data["results"]), 2)
        self.assertEqual(edit.status_code, 403)
        self.assertEqual(create_category.status_code, 403)

    def test_admin_can_create_edit_and_delete_categories_and_items(self):
        client = self.client_for(self.admin)

        category_response = client.post("/api/menu/categories/", {"name": "Tea", "display_order": 2}, format="json")
        self.assertEqual(category_response.status_code, 201)
        new_category_id = category_response.data["id"]
        category_edit = client.patch(
            f"/api/menu/categories/{new_category_id}/", {"display_order": 3}, format="json"
        )
        self.assertEqual(category_edit.status_code, 200)
        self.assertEqual(category_edit.data["display_order"], 3)
        item_response = client.post(
            "/api/menu/items/",
            {"category": new_category_id, "name": "Green Tea", "description": "Sencha", "price": "2.25", "is_available": True},
            format="json",
        )
        self.assertEqual(item_response.status_code, 201)
        item_id = item_response.data["id"]
        edit_response = client.patch(f"/api/menu/items/{item_id}/", {"price": "2.50"}, format="json")
        self.assertEqual(edit_response.status_code, 200)
        self.assertEqual(edit_response.data["price"], "2.50")
        self.assertEqual(client.delete(f"/api/menu/items/{item_id}/").status_code, 204)
        self.assertEqual(client.delete(f"/api/menu/categories/{new_category_id}/").status_code, 204)

    def test_prices_must_be_positive_decimal_values(self):
        client = self.client_for(self.admin)
        for price in ("0.00", "-0.01"):
            with self.subTest(price=price):
                response = client.post(
                    "/api/menu/items/",
                    {"category": self.category.pk, "name": f"Bad Price {price}", "price": price, "is_available": True},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("price", response.data)

        self.available.refresh_from_db()
        self.assertIsInstance(self.available.price, Decimal)

    def test_browse_page_requires_sign_in_and_shows_available_items(self):
        anonymous = self.client.get("/menu/")
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(self.customer)
        response = self.client.get("/menu/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flat White")
        self.assertNotContains(response, "Cold Brew")
        self.assertContains(response, "Add")
