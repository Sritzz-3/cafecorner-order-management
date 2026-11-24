from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from coupons.models import Coupon
from menu.models import Category
from orders.models import Order, PrintJob


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
