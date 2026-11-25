from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Profile


class AccountRoleTests(TestCase):
    def test_new_user_gets_customer_profile_and_group(self):
        user = User.objects.create_user(username="maya", password="safe-password-123")

        self.assertEqual(user.profile.role, Profile.Role.CUSTOMER)
        self.assertTrue(user.groups.filter(name="Customer").exists())

    def test_profile_role_change_updates_group(self):
        user = User.objects.create_user(username="sam", password="safe-password-123")
        user.profile.role = Profile.Role.STAFF
        user.profile.save()

        self.assertEqual(list(user.groups.values_list("name", flat=True)), ["Staff"])
        self.client.force_login(user)
        homepage = self.client.get("/")
        self.assertEqual(homepage.status_code, 200)
        self.assertContains(homepage, "Open the order queue")
        self.assertContains(homepage, 'data-bs-toggle="collapse"')
        self.assertContains(homepage, ">Queue</a>")

    def test_registration_creates_customer(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "new-customer",
                "email": "customer@example.com",
                "password1": "pass-word-401!",
                "password2": "pass-word-401!",
                "role": "ADMIN",
                "is_staff": "true",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="new-customer")
        self.assertEqual(user.profile.role, Profile.Role.CUSTOMER)
        self.assertFalse(user.is_staff)

    def test_current_profile_requires_login(self):
        response = self.client.get("/accounts/api/me/")

        self.assertEqual(response.status_code, 403)

    def test_current_profile_returns_role_for_authenticated_user(self):
        user = User.objects.create_user(username="api-customer", password="safe-password-123")
        User.objects.create_user(username="other-customer", password="safe-password-123")
        api_client = APIClient()
        api_client.force_authenticate(user=user)

        response = api_client.get("/accounts/api/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], Profile.Role.CUSTOMER)
        self.assertEqual(response.data["username"], "api-customer")
        self.assertNotIn("other-customer", str(response.data))

        self.client.force_login(user)
        homepage = self.client.get("/")
        self.assertTemplateUsed(homepage, "accounts/home.html")
        self.assertContains(homepage, "Browse the menu")
        self.assertContains(homepage, "My Orders")

    def test_profile_api_does_not_allow_role_updates(self):
        user = User.objects.create_user(username="api-safe", password="safe-password-123")
        api_client = APIClient()
        api_client.force_authenticate(user=user)

        response = api_client.put("/accounts/api/me/", {"role": "ADMIN"}, format="json")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(user.profile.role, Profile.Role.CUSTOMER)

    def test_missing_profile_is_recreated_with_safe_default(self):
        user = User.objects.create_superuser(username="root-user", email="root@example.com", password="safe-password-123")
        user.profile.delete()
        api_client = APIClient()
        api_client.force_authenticate(user=user)

        response = api_client.get("/accounts/api/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], Profile.Role.CUSTOMER)


class RoleNavigationAndLoginTests(TestCase):
    password = "safe-password-123"

    def create_role_user(self, username, role, *, superuser=False):
        if superuser:
            user = User.objects.create_superuser(
                username=username,
                email=f"{username}@example.com",
                password=self.password,
            )
        else:
            user = User.objects.create_user(username=username, password=self.password)
        user.profile.role = role
        user.profile.save()
        return user

    def login_with_role(self, username):
        return self.client.post(
            "/accounts/login/",
            {"username": username, "password": self.password},
        )

    def test_anonymous_navigation_shows_menu_login_register_only(self):
        response = self.client.get("/")

        self.assertContains(response, ">Menu</a>")
        self.assertContains(response, ">Login</a>")
        self.assertContains(response, ">Register</a>")
        self.assertNotContains(response, ">Queue</a>")
        self.assertNotContains(response, ">Dashboard</a>")
        self.assertNotContains(response, ">Admin</a>")
        self.assertNotContains(response, "Log out")

    def test_customer_navigation_shows_menu_cart_and_my_orders(self):
        user = self.create_role_user("nav-customer", Profile.Role.CUSTOMER)
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, ">Menu</a>")
        self.assertContains(response, ">Cart")
        self.assertContains(response, ">My Orders</a>")
        self.assertNotContains(response, ">Queue</a>")
        self.assertNotContains(response, ">Dashboard</a>")

    def test_staff_navigation_shows_menu_and_queue_without_admin_links(self):
        user = self.create_role_user("nav-staff", Profile.Role.STAFF)
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, ">Menu</a>")
        self.assertContains(response, ">Queue</a>")
        self.assertNotContains(response, ">Dashboard</a>")
        self.assertNotContains(response, ">Admin</a>")

    def test_admin_navigation_shows_dashboard_and_admin_link(self):
        user = self.create_role_user("nav-admin", Profile.Role.ADMIN, superuser=True)
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, ">Dashboard</a>")
        self.assertContains(response, ">Admin</a>")

    def test_logout_control_only_appears_for_signed_in_users(self):
        anonymous_response = self.client.get("/")
        self.assertNotContains(anonymous_response, "Log out")

        user = self.create_role_user("nav-logout", Profile.Role.CUSTOMER)
        self.client.force_login(user)
        signed_in_response = self.client.get("/")
        self.assertContains(signed_in_response, "Log out")

    def test_customer_login_redirects_to_menu(self):
        self.create_role_user("login-customer", Profile.Role.CUSTOMER)

        response = self.login_with_role("login-customer")

        self.assertRedirects(response, "/menu/", fetch_redirect_response=False)

    def test_staff_login_redirects_to_order_queue(self):
        self.create_role_user("login-staff", Profile.Role.STAFF)

        response = self.login_with_role("login-staff")

        self.assertRedirects(response, "/orders/queue/", fetch_redirect_response=False)

    def test_admin_login_redirects_to_dashboard(self):
        self.create_role_user("login-admin", Profile.Role.ADMIN)

        response = self.login_with_role("login-admin")

        self.assertRedirects(response, "/orders/dashboard/", fetch_redirect_response=False)
