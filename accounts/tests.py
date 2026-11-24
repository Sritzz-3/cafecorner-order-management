from django.contrib.auth.models import Group, User
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

    def test_registration_creates_customer(self):
        response = self.client.post(
            "/accounts/register/",
            {"username": "new-customer", "email": "customer@example.com", "password1": "pass-word-401!", "password2": "pass-word-401!"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username="new-customer").profile.role, Profile.Role.CUSTOMER)

    def test_current_profile_requires_login(self):
        response = self.client.get("/accounts/api/me/")

        self.assertEqual(response.status_code, 403)

    def test_current_profile_returns_role_for_authenticated_user(self):
        user = User.objects.create_user(username="api-customer", password="safe-password-123")
        api_client = APIClient()
        api_client.force_authenticate(user=user)

        response = api_client.get("/accounts/api/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], Profile.Role.CUSTOMER)
