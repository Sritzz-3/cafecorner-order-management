from django.urls import path

from menu.views import browse_menu

urlpatterns = [path("", browse_menu, name="browse-menu")]
