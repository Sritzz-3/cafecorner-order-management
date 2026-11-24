# CafeCorner

A cafe ordering and operations app built with Python, Django, and Django REST Framework.

The dashboard uses `Asia/Kolkata` local dates. Revenue and top-item sales are based on orders whose `collected_at` timestamp falls today and whose status is `COLLECTED`.

## How to run the demo

On macOS, from the project folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Replace the example `SECRET_KEY` in `.env` with a local random value before exposing the app outside your machine. Demo-data seeding is still being added; for now, create a superuser with `python manage.py createsuperuser`, then use Django admin to add menu categories and items. The customer, staff, and manager pages become useful after creating users and assigning their profile roles.

## Pages

- Customer menu: `/menu/`
- Customer cart: `/orders/cart/`
- Customer order tracking: `/orders/mine/`
- Staff queue: `/orders/queue/`
- Manager dashboard: `/orders/dashboard/`
- API docs: `/api/docs/`

## Impact

The coupon workflow is designed to prevent a completed order's reward from being lost between collection and redemption. Each collected order receives a uniquely coded, expiring coupon; the database records redemption atomically, including who redeemed it and when.
