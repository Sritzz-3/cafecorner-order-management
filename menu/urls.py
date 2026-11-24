from rest_framework.routers import DefaultRouter

from menu.api import CategoryViewSet, MenuItemViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="menu-category")
router.register("items", MenuItemViewSet, basename="menu-item")

urlpatterns = router.urls
