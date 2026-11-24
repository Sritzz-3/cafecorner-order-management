from rest_framework.routers import SimpleRouter

from printer_api.api import PrintJobViewSet

router = SimpleRouter()
router.register("", PrintJobViewSet, basename="print-job")

urlpatterns = router.urls
