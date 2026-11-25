# CafeCorner

CafeCorner is a small cafe order-management demo built with Django and Django REST Framework. Customers browse a menu and place orders; staff manage the queue and redeem coupons; admins manage the menu and view daily sales; a separate client polls for receipt-print jobs.

This project is licensed under the [MIT License](LICENSE).

## Features

- Role-based customer, staff, admin, and printer access.
- Menu browsing, cart checkout, order tracking, and a live staff queue.
- Server-calculated INR totals and saved unit-price snapshots.
- Atomic order-state changes, status history, and daily collected-order dashboard.
- Single-use, expiring coupons and separate order/coupon print jobs.
- Token-restricted printer API, console printer client, and optional ESC/POS thermal backend.
- Paginated REST API with interactive docs at `/api/docs/`.

## Tech stack

Python 3.9 and 3.11 are supported and tested in CI. The app uses Django 4.2, Django REST Framework, SQLite for local development, drf-spectacular, Bootstrap, and vanilla JavaScript. The standalone printer client uses `requests`; `python-escpos` is an optional thermal-printer dependency.

## Run on macOS

From the repository root, with Python 3 installed:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
unset DEBUG
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. `seed_demo` is development-only and refuses to run when `DEBUG=False`. It prints the demo usernames and obviously fake shared passwords. It prints the printer token only on the first seed run; save it then if you intend to run the printer client. Do not use these demo credentials outside a local demo.

## Demo walkthrough

1. Sign in as `cafecorner_demo_customer` using the password printed by `seed_demo`; browse `/menu/`, add items to the cart, and place an order. View live status at `/orders/mine/`.
2. Sign in as `cafecorner_demo_staff` in another browser session and open `/orders/queue/`. Advance the new order from PLACED through PREPARING and READY to COLLECTED. A coupon and coupon-slip job are created on collection.
3. To redeem a coupon, first run the console printer client below and collect its printed coupon slip. Sign in as staff and POST `{"code":"..."}` to `/api/coupons/redeem/` (for example, with the API UI or an API client). Redemption is for staff at the counter on a customer's behalf.
4. Run the printer client in console mode using the one-time `PRINTER_TOKEN` from the seed output:

   ```sh
   python3 -m venv printer_client/.venv
   source printer_client/.venv/bin/activate
   python -m pip install -r printer_client/requirements.txt
   export API_URL=http://127.0.0.1:8000/api
   export PRINTER_TOKEN='paste-the-seed-token-here'
   export PRINTER_BACKEND=console
   python printer_client/client.py
   ```

   Pending order and coupon slips appear in the terminal and `printed_slips.txt`. See [`printer_client/README.md`](printer_client/README.md) for optional settings and the Raspberry Pi service example.

Pages: menu `/menu/`, cart `/orders/cart/`, my orders `/orders/mine/`, staff queue `/orders/queue/`, and admin dashboard `/orders/dashboard/`. REST API documentation: `/api/docs/`.

## Tests

The root requirements install both the Django app dependencies and the printer client's minimal `requests` dependencies in one step. Run both suites from the repository root:

```sh
python manage.py test
python -m unittest discover -s printer_client/tests
```

The Django suite contains 59 tests; the standalone printer-client suite contains 7 (66 total).

For coverage (install requirements first):

```sh
coverage run manage.py test
coverage run --append -m unittest discover -s printer_client/tests
coverage report
```

## Screenshots

_Screenshots will be added here._

## What is and isn't tested on real hardware

The app and console printer client are exercised locally; printer HTTP interactions are mocked in the client unit tests. **The optional thermal backend, USB/network device settings, and physical receipt output have not been tested on real hardware.**

## Impact

When a cafe relies on a verbal or handwritten reward slip, a coupon can be lost between collecting an order and redeeming the reward. CafeCorner creates an expiring coupon in the same database transaction as collection, records redemption atomically with the staff member and time, and queues a separate coupon slip for printing. This makes the reward traceable through the demo workflow; it does not claim a measured business saving.
