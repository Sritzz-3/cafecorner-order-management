from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import Profile
from coupons.models import Coupon
from menu.models import Category, MenuItem
from orders.models import Order, PrintJob
from orders.services import place_order


class PrintJobApiTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="print-customer", password="safe-pass-123")
        self.staff = User.objects.create_user(username="print-staff", password="safe-pass-123")
        self.staff.profile.role = Profile.Role.STAFF
        self.staff.profile.save()
        self.admin = User.objects.create_user(username="print-admin", password="safe-pass-123")
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save()
        self.printer = User.objects.create_user(username="print-device", password=None)
        self.printer.profile.role = Profile.Role.PRINTER
        self.printer.profile.save()
        self.token = Token.objects.create(user=self.printer)
        category = Category.objects.create(name="Print test menu")
        self.item = MenuItem.objects.create(category=category, name="Vanilla Latte", price="4.60")
        self.order = place_order(self.customer, [{"menu_item_id": self.item.pk, "quantity": 2}])
        self.order_job = self.order.print_jobs.get(kind=PrintJob.Kind.ORDER_SLIP)

    def printer_client(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        return client

    def session_client(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_pending_jobs_are_oldest_first_limited_and_include_print_details(self):
        later_order = place_order(self.customer, [{"menu_item_id": self.item.pk, "quantity": 1}])
        client = self.printer_client()

        response = client.get("/api/print-jobs/pending/?limit=1")
        invalid_limit = client.get("/api/print-jobs/pending/?limit=101")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        job = response.data["results"][0]
        self.assertEqual(job["id"], self.order_job.pk)
        self.assertEqual(job["kind"], PrintJob.Kind.ORDER_SLIP)
        self.assertEqual(job["order"]["items"][0]["item_name"], "Vanilla Latte")
        self.assertEqual(job["order"]["items"][0]["quantity"], 2)
        self.assertNotIn("coupon_code", job)
        self.assertEqual(invalid_limit.status_code, 400)
        self.assertNotEqual(later_order.pk, self.order.pk)

    def test_coupon_code_is_only_in_coupon_slip_jobs_for_printer(self):
        self.order.advance(self.staff)
        self.order.advance(self.staff)
        self.order.advance(self.staff)
        coupon = Coupon.objects.get(order=self.order)

        response = self.printer_client().get("/api/print-jobs/pending/")
        jobs = {job["kind"]: job for job in response.data["results"]}

        self.assertNotIn("coupon_code", jobs[PrintJob.Kind.ORDER_SLIP])
        self.assertEqual(jobs[PrintJob.Kind.COUPON_SLIP]["coupon_code"], coupon.code)
        self.assertIn("coupon_expires_at", jobs[PrintJob.Kind.COUPON_SLIP])

        staff_order = self.session_client(self.staff).get(f"/api/orders/{self.order.pk}/")
        self.assertEqual(staff_order.status_code, 200)
        self.assertNotIn("coupon_code", staff_order.data)

    def test_claim_is_atomic_and_second_client_gets_409(self):
        first = self.printer_client().post(f"/api/print-jobs/{self.order_job.pk}/claim/")
        second = self.printer_client().post(f"/api/print-jobs/{self.order_job.pk}/claim/")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["status"], PrintJob.Status.PRINTING)
        self.assertIsNotNone(first.data["claimed_at"])
        self.assertEqual(second.status_code, 409)

    def test_claim_timeout_releases_job_for_a_new_printer_claim(self):
        client = self.printer_client()
        self.assertEqual(client.post(f"/api/print-jobs/{self.order_job.pk}/claim/").status_code, 200)
        PrintJob.objects.filter(pk=self.order_job.pk).update(
            claimed_at=timezone.now() - timedelta(seconds=settings.PRINT_CLAIM_TIMEOUT_SECONDS + 10)
        )

        pending = client.get("/api/print-jobs/pending/")
        reclaimed = client.post(f"/api/print-jobs/{self.order_job.pk}/claim/")

        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.data["results"][0]["status"], PrintJob.Status.PENDING)
        self.assertEqual(reclaimed.status_code, 200)
        self.assertEqual(reclaimed.data["status"], PrintJob.Status.PRINTING)

    def test_printed_only_accepts_printing_jobs(self):
        client = self.printer_client()
        pending_conflict = client.post(f"/api/print-jobs/{self.order_job.pk}/printed/")
        pending_failure = client.post(
            f"/api/print-jobs/{self.order_job.pk}/failed/", {"error": "Not claimed"}, format="json"
        )
        client.post(f"/api/print-jobs/{self.order_job.pk}/claim/")
        printed = client.post(f"/api/print-jobs/{self.order_job.pk}/printed/")
        duplicate_conflict = client.post(f"/api/print-jobs/{self.order_job.pk}/printed/")

        self.assertEqual(pending_conflict.status_code, 409)
        self.assertEqual(pending_failure.status_code, 409)
        self.assertEqual(printed.status_code, 200)
        self.assertEqual(printed.data["status"], PrintJob.Status.PRINTED)
        self.assertIsNotNone(printed.data["printed_at"])
        self.assertEqual(duplicate_conflict.status_code, 409)

    @override_settings(PRINT_MAX_RETRIES=2)
    def test_failures_retry_then_stay_failed_until_staff_requeues(self):
        client = self.printer_client()

        client.post(f"/api/print-jobs/{self.order_job.pk}/claim/")
        first_failure = client.post(
            f"/api/print-jobs/{self.order_job.pk}/failed/", {"error": "Paper jam"}, format="json"
        )
        client.post(f"/api/print-jobs/{self.order_job.pk}/claim/")
        final_failure = client.post(
            f"/api/print-jobs/{self.order_job.pk}/failed/", {"error": "Printer still jammed"}, format="json"
        )
        cannot_claim_failed = client.post(f"/api/print-jobs/{self.order_job.pk}/claim/")

        self.assertEqual(first_failure.status_code, 200)
        self.assertEqual(first_failure.data["status"], PrintJob.Status.PENDING)
        self.assertEqual(first_failure.data["retry_count"], 1)
        self.assertEqual(final_failure.status_code, 200)
        self.assertEqual(final_failure.data["status"], PrintJob.Status.FAILED)
        self.assertEqual(final_failure.data["retry_count"], 2)
        self.assertEqual(cannot_claim_failed.status_code, 409)

        staff_page = self.session_client(self.staff).get("/orders/queue/")
        self.assertContains(staff_page, "Printer still jammed")
        requeued = self.session_client(self.staff).post(f"/api/print-jobs/{self.order_job.pk}/requeue/")
        self.assertEqual(requeued.status_code, 200)
        self.assertEqual(requeued.data["status"], PrintJob.Status.PENDING)
        self.assertEqual(requeued.data["retry_count"], 0)
        self.assertEqual(
            self.session_client(self.staff).post(f"/api/print-jobs/{self.order_job.pk}/requeue/").status_code,
            409,
        )

    def test_staff_sessions_are_limited_to_requeue_and_customer_cannot_requeue(self):
        PrintJob.objects.filter(pk=self.order_job.pk).update(status=PrintJob.Status.FAILED)
        staff = self.session_client(self.staff)
        customer = self.session_client(self.customer)

        self.assertEqual(staff.get("/api/print-jobs/pending/").status_code, 403)
        self.assertEqual(staff.post(f"/api/print-jobs/{self.order_job.pk}/claim/").status_code, 403)
        self.assertEqual(staff.post(f"/api/print-jobs/{self.order_job.pk}/printed/").status_code, 403)
        self.assertEqual(staff.post(f"/api/print-jobs/{self.order_job.pk}/failed/", {"error": "x"}).status_code, 403)
        self.assertEqual(customer.post(f"/api/print-jobs/{self.order_job.pk}/requeue/").status_code, 403)
        self.assertEqual(staff.post(f"/api/print-jobs/{self.order_job.pk}/requeue/").status_code, 200)

        PrintJob.objects.filter(pk=self.order_job.pk).update(status=PrintJob.Status.FAILED)
        self.assertEqual(
            self.session_client(self.admin).post(f"/api/print-jobs/{self.order_job.pk}/requeue/").status_code,
            200,
        )

    def test_printer_token_is_denied_by_all_other_api_families(self):
        self.order.advance(self.staff)
        self.order.advance(self.staff)
        self.order.advance(self.staff)
        paths = (
            ("get", "/api/menu/items/", None),
            ("get", "/api/menu/categories/", None),
            ("get", "/api/orders/", None),
            ("get", "/api/orders/mine/", None),
            ("get", "/api/orders/queue/", None),
            ("get", f"/api/orders/{self.order.pk}/history/", None),
            ("post", f"/api/orders/{self.order.pk}/advance/", None),
            ("get", "/accounts/api/me/", None),
            ("get", "/api/coupons/", None),
            ("post", "/api/coupons/redeem/", {"code": self.order.coupon.code}),
            ("post", f"/api/print-jobs/{self.order_job.pk}/requeue/", None),
        )
        client = self.printer_client()

        for method, path, data in paths:
            with self.subTest(path=path):
                response = getattr(client, method)(path, data, format="json") if data is not None else getattr(client, method)(path)
                self.assertEqual(response.status_code, 403)

        self.assertEqual(self.session_client(self.admin).get("/api/print-jobs/pending/").status_code, 403)

    def test_create_printer_user_command_prints_token_once_and_assigns_limited_role(self):
        output = StringIO()
        call_command("create_printer_user", username="new-printer", stdout=output)
        user = User.objects.get(username="new-printer")
        token = Token.objects.get(user=user)

        self.assertIn(f"PRINTER_TOKEN={token.key}", output.getvalue())
        self.assertEqual(user.profile.role, Profile.Role.PRINTER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        with self.assertRaises(CommandError):
            call_command("create_printer_user", username="new-printer", stdout=StringIO())


class DemoSeedCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_seed_is_idempotent_and_prints_fake_demo_credentials(self):
        output = StringIO()
        call_command("seed_demo", stdout=output)
        self.assertIn("cafecorner_demo_customer", output.getvalue())
        self.assertIn("DEMO-ONLY-not-a-real-password-123!", output.getvalue())
        self.assertIn("PRINTER_TOKEN=", output.getvalue())
        self.assertEqual(Order.objects.filter(customer__username="cafecorner_demo_customer").count(), 5)
        self.assertEqual(Order.objects.filter(status=Order.Status.COLLECTED).count(), 1)
        self.assertEqual(Coupon.objects.count(), 1)
        self.assertEqual(PrintJob.objects.count(), 6)

        second_output = StringIO()
        call_command("seed_demo", stdout=second_output)
        self.assertEqual(Order.objects.filter(customer__username="cafecorner_demo_customer").count(), 5)
        self.assertEqual(Coupon.objects.count(), 1)
        self.assertEqual(PrintJob.objects.count(), 6)
        self.assertIn("was not displayed again", second_output.getvalue())

    @override_settings(DEBUG=False)
    def test_seed_refuses_to_run_when_debug_is_false(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)
