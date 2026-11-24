app_name = "order_pages"

from django.urls import path

from orders.page_views import admin_dashboard, cart_page, my_orders_page, staff_queue_page

urlpatterns = [
    path("cart/", cart_page, name="cart"),
    path("mine/", my_orders_page, name="mine"),
    path("queue/", staff_queue_page, name="queue"),
    path("dashboard/", admin_dashboard, name="dashboard"),
]
