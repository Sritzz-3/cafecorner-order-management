from django.contrib.auth import views as auth_views
from django.urls import path

from accounts.api import CurrentProfileView
from accounts.views import RoleBasedLoginView, register

urlpatterns = [
    path("register/", register, name="register"),
    path("login/", RoleBasedLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/me/", CurrentProfileView.as_view(), name="current-profile"),
]
