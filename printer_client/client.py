#!/usr/bin/env python3
import logging
import os
import time

import requests

from printer_client.printers import create_printer


class PrinterClient:
    def __init__(
        self,
        api_url,
        token,
        printer,
        poll_interval=5,
        max_backoff=60,
        session=None,
        sleep_fn=time.sleep,
        logger=None,
    ):
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.printer = printer
        self.poll_interval = max(0.1, float(poll_interval))
        self.max_backoff = max(self.poll_interval, float(max_backoff))
        self.session = session or requests.Session()
        self.sleep = sleep_fn
        self.logger = logger or logging.getLogger("cafecorner-printer")

    @property
    def headers(self):
        return {"Authorization": f"Token {self.token}", "Accept": "application/json"}

    def _url(self, path):
        return f"{self.api_url}/print-jobs/{path.lstrip('/')}"

    def _list_pending(self):
        response = self.session.get(self._url("pending/?limit=20"), headers=self.headers, timeout=10)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return body.get("results", [])
        return body

    def _record_failure(self, job_id, error):
        try:
            response = self.session.post(
                self._url(f"{job_id}/failed/"),
                headers=self.headers,
                json={"error": str(error)[:1000]},
                timeout=10,
            )
            if response.status_code == 409:
                self.logger.warning("Job %s was no longer claimed when failure was reported.", job_id)
                return True
            response.raise_for_status()
            result = response.json()
            self.logger.error(
                "Print failed for job %s; server status=%s retry=%s.",
                job_id,
                result.get("status"),
                result.get("retry_count"),
            )
            return True
        except requests.RequestException:
            self.logger.exception("Could not report failure for print job %s.", job_id)
            return False

    def process_once(self):
        try:
            jobs = self._list_pending()
        except requests.RequestException:
            self.logger.exception("Could not reach the print-job API.")
            return False
        if not isinstance(jobs, list):
            self.logger.error("The print-job API returned a malformed job list.")
            return False

        for pending_job in jobs:
            try:
                job_id = int(pending_job["id"])
            except (KeyError, TypeError, ValueError):
                self.logger.error("Skipping a malformed pending print job: %r", pending_job)
                continue
            try:
                claim = self.session.post(self._url(f"{job_id}/claim/"), headers=self.headers, timeout=10)
                if claim.status_code == 409:
                    self.logger.info("Another printer claimed job %s first.", job_id)
                    continue
                claim.raise_for_status()
                job = claim.json()
            except requests.RequestException:
                self.logger.exception("Could not claim print job %s.", job_id)
                return False

            try:
                if job["kind"] == "ORDER_SLIP":
                    self.printer.print_order_slip(job)
                elif job["kind"] == "COUPON_SLIP":
                    self.printer.print_coupon_slip(job)
                else:
                    raise ValueError(f"Unsupported print job kind: {job['kind']}")
            except Exception as exc:  # A broken device or malformed slip must not stop later jobs.
                self.logger.exception("Printing job %s failed.", job_id)
                if not self._record_failure(job_id, exc):
                    return False
                continue

            try:
                response = self.session.post(self._url(f"{job_id}/printed/"), headers=self.headers, timeout=10)
                if response.status_code == 409:
                    self.logger.warning("Job %s was no longer claimed when printed status was reported.", job_id)
                    continue
                response.raise_for_status()
                self.logger.info("Printed job %s (%s).", job_id, job["kind"])
            except requests.RequestException:
                self.logger.exception("Could not mark print job %s as printed.", job_id)
                return False
        return True

    def run(self, max_cycles=None):
        delay = self.poll_interval
        cycles = 0
        try:
            while max_cycles is None or cycles < max_cycles:
                cycles += 1
                successful_cycle = self.process_once()
                wait = self.poll_interval if successful_cycle else delay
                self.sleep(wait)
                if successful_cycle:
                    delay = self.poll_interval
                else:
                    delay = min(delay * 2, self.max_backoff)
        except KeyboardInterrupt:
            self.logger.info("Printer client shutting down.")


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")
    api_url = os.environ.get("API_URL")
    token = os.environ.get("PRINTER_TOKEN")
    if not api_url or not token:
        raise SystemExit("Set API_URL and PRINTER_TOKEN before starting the printer client.")
    try:
        interval = float(os.environ.get("POLL_INTERVAL", "5"))
        width = int(os.environ.get("RECEIPT_WIDTH", "42"))
    except ValueError as exc:
        raise SystemExit(f"Invalid polling interval or receipt width: {exc}")
    backend = os.environ.get("PRINTER_BACKEND", "console").lower()
    printer = create_printer(backend=backend, width=width)
    client = PrinterClient(api_url, token, printer, poll_interval=interval)
    try:
        client.run()
    finally:
        printer.close()


if __name__ == "__main__":
    main()
