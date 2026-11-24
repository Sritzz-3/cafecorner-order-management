import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

from printer_client.client import PrinterClient
from printer_client.formatter import format_coupon_slip, format_order_slip
from printer_client.printers import ConsolePrinter


class FakeResponse:
    def __init__(self, data=None, status_code=200):
        self.data = data or {}
        self.status_code = status_code

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class RecordingPrinter:
    def __init__(self, fail=False):
        self.fail = fail
        self.orders = []
        self.coupons = []

    def print_order_slip(self, job):
        if self.fail:
            raise OSError("paper feed failed")
        self.orders.append(job)

    def print_coupon_slip(self, job):
        if self.fail:
            raise OSError("paper feed failed")
        self.coupons.append(job)


def order_job(job_id=7):
    return {
        "id": job_id,
        "kind": "ORDER_SLIP",
        "order": {
            "id": 42,
            "created_at": "2026-11-25T10:30:00+05:30",
            "total": "9.00",
            "items": [{"item_name": "Flat white", "quantity": 2, "unit_price": "4.50", "line_total": "9.00"}],
        },
    }


class PrinterClientTests(unittest.TestCase):
    def setUp(self):
        self.job = order_job()
        self.claimed = FakeResponse(self.job)
        self.session = Mock()
        self.session.get.return_value = FakeResponse({"count": 1, "results": [self.job]})
        self.session.post.side_effect = [self.claimed, FakeResponse({"status": "PRINTED"})]
        self.printer = RecordingPrinter()
        self.client = PrinterClient(
            "http://cafe.test/api",
            "secret-token",
            self.printer,
            session=self.session,
            sleep_fn=Mock(),
            logger=Mock(),
        )

    def test_successful_poll_claim_print_and_marked_printed(self):
        self.assertTrue(self.client.process_once())

        self.assertEqual(len(self.printer.orders), 1)
        self.assertEqual(self.session.get.call_args.args[0], "http://cafe.test/api/print-jobs/pending/?limit=20")
        self.assertIn("Token secret-token", self.session.get.call_args.kwargs["headers"]["Authorization"])
        self.assertEqual(self.session.post.call_args_list[0].args[0], "http://cafe.test/api/print-jobs/7/claim/")
        self.assertEqual(self.session.post.call_args_list[1].args[0], "http://cafe.test/api/print-jobs/7/printed/")

    def test_coupon_jobs_use_the_coupon_slip_backend_method(self):
        coupon = {
            "id": 8,
            "kind": "COUPON_SLIP",
            "coupon_code": "ABCD2345EFGH6789JKLMNPQR",
            "coupon_expires_at": "2026-12-25T10:30:00+05:30",
            "order": self.job["order"],
        }
        self.session.get.return_value = FakeResponse({"results": [coupon]})
        self.session.post.side_effect = [FakeResponse(coupon), FakeResponse({"status": "PRINTED"})]

        self.assertTrue(self.client.process_once())

        self.assertEqual(self.printer.coupons, [coupon])

    def test_claim_conflict_skips_the_job_without_printing(self):
        self.session.post.side_effect = [FakeResponse(status_code=409)]

        self.assertTrue(self.client.process_once())

        self.assertEqual(self.printer.orders, [])
        self.session.post.assert_called_once()

    def test_print_failure_is_reported_to_the_server(self):
        self.printer.fail = True
        self.session.post.side_effect = [self.claimed, FakeResponse({"status": "PENDING", "retry_count": 1})]

        self.assertTrue(self.client.process_once())

        failure_call = self.session.post.call_args_list[1]
        self.assertEqual(failure_call.args[0], "http://cafe.test/api/print-jobs/7/failed/")
        self.assertIn("paper feed failed", failure_call.kwargs["json"]["error"])

    def test_network_failures_back_off_and_the_loop_continues(self):
        self.session.get.side_effect = [
            requests.ConnectionError("offline"),
            requests.Timeout("still offline"),
            FakeResponse({"count": 0, "results": []}),
        ]
        sleeps = []
        client = PrinterClient(
            "http://cafe.test/api",
            "secret-token",
            self.printer,
            poll_interval=1,
            max_backoff=2,
            session=self.session,
            sleep_fn=sleeps.append,
            logger=Mock(),
        )

        client.run(max_cycles=3)

        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(sleeps, [1, 2, 1])

    def test_receipt_formatting_respects_both_supported_widths(self):
        coupon = {
            "kind": "COUPON_SLIP",
            "coupon_code": "ABCD2345EFGH6789JKLMNPQR",
            "coupon_expires_at": "2026-12-25T10:30:00+05:30",
            "order": self.job["order"],
        }
        for width in (32, 42):
            with self.subTest(width=width):
                order_text = format_order_slip(self.job, width)
                coupon_text = format_coupon_slip(coupon, width)
                self.assertTrue(all(len(line) <= width for line in order_text.splitlines()))
                self.assertTrue(all(len(line) <= width for line in coupon_text.splitlines()))
                self.assertIn("ORDER #42", order_text)
                self.assertIn("2 x Flat", order_text)
                self.assertIn("TOTAL", order_text)
                self.assertIn(coupon["coupon_code"], coupon_text)
                self.assertIn("Expires:", coupon_text)

    def test_console_backend_appends_the_formatted_slip_to_a_text_file(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "receipts.txt"
            printer = ConsolePrinter(width=32, output_file=output)
            with patch("builtins.print") as terminal:
                printer.print_order_slip(self.job)

            self.assertIn("ORDER #42", output.read_text(encoding="utf-8"))
            terminal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
