from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Profile
from coupons.models import CODE_ALPHABET, CODE_LENGTH, Coupon
from coupons.services import CouponAlreadyUsed, CouponExpired, CouponNotFound, redeem_coupon
from menu.models import Category, MenuItem
from orders.models import Order, PrintJob
from orders.services import place_order


class CouponWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="coupon-customer", password="safe-pass-123")
        self.staff = User.objects.create_user(username="coupon-staff", password="safe-pass-123")
        self.staff.profile.role = Profile.Role.STAFF
        self.staff.profile.save()
        self.manager = User.objects.create_user(username="coupon-manager", password="safe-pass-123")
        self.manager.profile.role = Profile.Role.ADMIN
        self.manager.profile.save()
        category = Category.objects.create(name="Rewards")
        self.item = MenuItem.objects.create(category=category, name="Cafe Mocha", price="5.25")

    def place_order(self):
        return place_order(self.customer, [{"menu_item_id": self.item.pk, "quantity": 1}])

    def collect(self, order):
        order.advance(self.staff)
        order.advance(self.staff)
        order.advance(self.staff)

    def test_collected_orders_get_unique_hard_to_guess_coupons_and_coupon_print_jobs(self):
        first = self.place_order()
        second = self.place_order()
        self.assertFalse(Coupon.objects.filter(order=first).exists())
        self.assertFalse(first.print_jobs.filter(kind=PrintJob.Kind.COUPON_SLIP).exists())

        self.collect(first)
        self.collect(second)
        first_coupon = Coupon.objects.get(order=first)
        second_coupon = Coupon.objects.get(order=second)

        self.assertEqual(len(first_coupon.code), CODE_LENGTH)
        self.assertTrue(set(first_coupon.code).issubset(set(CODE_ALPHABET)))
        self.assertNotEqual(first_coupon.code, second_coupon.code)
        self.assertAlmostEqual((first_coupon.expires_at - timezone.now()).total_seconds(), 30 * 24 * 60 * 60, delta=2)
        self.assertTrue(first.print_jobs.filter(kind=PrintJob.Kind.COUPON_SLIP, status=PrintJob.Status.PENDING).exists())
        collected_event = first.history.get(new_status=Order.Status.COLLECTED)
        self.assertLess(abs((first.collected_at - collected_event.changed_at).total_seconds()), 1)

    def test_coupon_expiry_uses_configured_validity_days(self):
        order = self.place_order()
        with override_settings(COUPON_VALIDITY_DAYS=5):
            self.collect(order)

        coupon = Coupon.objects.get(order=order)
        self.assertAlmostEqual((coupon.expires_at - timezone.now()).total_seconds(), 5 * 24 * 60 * 60, delta=2)

    def test_cancelled_orders_do_not_get_coupons(self):
        order = self.place_order()
        order.transition_to(Order.Status.CANCELLED, self.customer)

        self.assertFalse(Coupon.objects.filter(order=order).exists())
        self.assertFalse(order.print_jobs.filter(kind=PrintJob.Kind.COUPON_SLIP).exists())
        self.assertIsNone(order.collected_at)

    def test_coupon_print_failure_rolls_back_collected_transition_and_coupon(self):
        order = self.place_order()
        order.advance(self.staff)
        order.advance(self.staff)
        prior_history_count = order.history.count()

        with patch("coupons.services.PrintJob.objects.create", side_effect=RuntimeError("printer queue unavailable")):
            with self.assertRaises(RuntimeError):
                order.advance(self.staff)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY)
        self.assertIsNone(order.collected_at)
        self.assertEqual(order.history.count(), prior_history_count)
        self.assertFalse(Coupon.objects.filter(order=order).exists())
        self.assertFalse(order.print_jobs.filter(kind=PrintJob.Kind.COUPON_SLIP).exists())

    def test_staff_redemption_records_actor_and_time_and_cannot_be_reused(self):
        order = self.place_order()
        self.collect(order)
        coupon = Coupon.objects.get(order=order)

        redeemed = redeem_coupon(coupon.code, self.staff)

        self.assertTrue(redeemed.is_redeemed)
        self.assertEqual(redeemed.redeemed_by, self.staff)
        self.assertIsNotNone(redeemed.redeemed_at)
        with self.assertRaises(CouponAlreadyUsed):
            redeem_coupon(coupon.code, self.manager)

    def test_expired_and_unknown_codes_have_distinct_staff_errors(self):
        order = self.place_order()
        self.collect(order)
        coupon = Coupon.objects.get(order=order)
        Coupon.objects.filter(pk=coupon.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

        with self.assertRaises(CouponExpired):
            redeem_coupon(coupon.code, self.staff)
        with self.assertRaises(CouponNotFound):
            redeem_coupon("NO-SUCH-COUPON-CODE", self.staff)


class CouponApiTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="api-coupon-customer", password="safe-pass-123")
        self.other_customer = User.objects.create_user(username="api-coupon-other", password="safe-pass-123")
        self.staff = User.objects.create_user(username="api-coupon-staff", password="safe-pass-123")
        self.staff.profile.role = Profile.Role.STAFF
        self.staff.profile.save()
        category = Category.objects.create(name="Api rewards")
        self.item = MenuItem.objects.create(category=category, name="Tea", price="2.50")
        self.order = place_order(self.customer, [{"menu_item_id": self.item.pk, "quantity": 1}])
        self.order.advance(self.staff)
        self.order.advance(self.staff)
        self.order.advance(self.staff)
        self.coupon = Coupon.objects.get(order=self.order)
        self.other_order = place_order(self.other_customer, [{"menu_item_id": self.item.pk, "quantity": 1}])
        self.other_order.advance(self.staff)
        self.other_order.advance(self.staff)
        self.other_order.advance(self.staff)
        self.other_coupon = Coupon.objects.get(order=self.other_order)

    def client_for(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def test_customers_view_only_their_coupons_and_cannot_redeem(self):
        client = self.client_for(self.customer)

        listing = client.get("/api/coupons/")
        foreign = client.get(f"/api/coupons/{self.other_coupon.pk}/")
        redeem = client.post("/api/coupons/redeem/", {"code": self.coupon.code}, format="json")

        self.assertEqual([row["code"] for row in listing.data["results"]], [self.coupon.code])
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(redeem.status_code, 403)

    def test_anonymous_redeem_errors_do_not_reveal_if_code_exists(self):
        client = self.client_for()
        existing = client.post("/api/coupons/redeem/", {"code": self.coupon.code}, format="json")
        missing = client.post("/api/coupons/redeem/", {"code": "UNKNOWN-COUPON-CODE"}, format="json")

        self.assertEqual(existing.status_code, missing.status_code)
        self.assertEqual(existing.data, missing.data)

    def test_staff_can_redeem_and_receives_clear_already_used_and_expired_errors(self):
        client = self.client_for(self.staff)
        success = client.post("/api/coupons/redeem/", {"code": self.coupon.code.lower()}, format="json")
        self.assertEqual(success.status_code, 200)
        self.assertTrue(success.data["is_redeemed"])
        self.assertEqual(success.data["redeemed_by"], self.staff.pk)

        used = client.post("/api/coupons/redeem/", {"code": self.coupon.code}, format="json")
        self.assertEqual(used.status_code, 409)
        self.assertEqual(used.data["detail"], "Coupon has already been redeemed.")

        Coupon.objects.filter(pk=self.other_coupon.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = client.post("/api/coupons/redeem/", {"code": self.other_coupon.code}, format="json")
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(expired.data["detail"], "Coupon has expired.")

        unknown = client.post("/api/coupons/redeem/", {"code": "UNKNOWN-COUPON-CODE"}, format="json")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.data["detail"], "Coupon code is invalid.")

    def test_redeem_endpoint_is_rate_limited(self):
        cache.clear()
        client = self.client_for(self.staff)
        with patch("rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES", {"coupon_redeem": "2/min"}):
            first = client.post("/api/coupons/redeem/", {"code": "MISSING-ONE"}, format="json")
            second = client.post("/api/coupons/redeem/", {"code": "MISSING-TWO"}, format="json")
            third = client.post("/api/coupons/redeem/", {"code": "MISSING-THREE"}, format="json")

        self.assertEqual((first.status_code, second.status_code, third.status_code), (404, 404, 429))
        cache.clear()


class CouponConcurrentRedemptionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.customer = User.objects.create_user(username="race-customer", password="safe-pass-123")
        self.staff_a = User.objects.create_user(username="race-staff-a", password="safe-pass-123")
        self.staff_a.profile.role = Profile.Role.STAFF
        self.staff_a.profile.save()
        self.staff_b = User.objects.create_user(username="race-staff-b", password="safe-pass-123")
        self.staff_b.profile.role = Profile.Role.STAFF
        self.staff_b.profile.save()
        category = Category.objects.create(name="Race rewards")
        item = MenuItem.objects.create(category=category, name="Americano", price="3.00")
        order = place_order(self.customer, [{"menu_item_id": item.pk, "quantity": 1}])
        order.advance(self.staff_a)
        order.advance(self.staff_a)
        order.advance(self.staff_a)
        self.coupon = Coupon.objects.get(order=order)

    def test_two_callers_with_the_same_stale_unredeemed_read_cannot_both_redeem(self):
        first_read = Coupon.objects.get(pk=self.coupon.pk)
        second_read = Coupon.objects.get(pk=self.coupon.pk)
        self.assertFalse(first_read.is_redeemed)
        self.assertFalse(second_read.is_redeemed)

        first = redeem_coupon(first_read.code, self.staff_a)
        with self.assertRaises(CouponAlreadyUsed):
            redeem_coupon(second_read.code, self.staff_b)

        self.assertEqual(first.redeemed_by, self.staff_a)
        self.assertEqual(Coupon.objects.get(pk=self.coupon.pk).redeemed_by, self.staff_a)
