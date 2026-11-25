from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.forms import CustomerRegistrationForm
from accounts.models import Profile


def home(request):
    return render(request, "accounts/home.html")


class RoleBasedLoginView(LoginView):
    template_name = "accounts/login.html"

    def get_default_redirect_url(self):
        user = self.request.user
        if user.is_superuser:
            return reverse("order_pages:dashboard")

        profile, _ = Profile.objects.get_or_create(user=user)
        destinations = {
            Profile.Role.CUSTOMER: "browse-menu",
            Profile.Role.STAFF: "order_pages:queue",
            Profile.Role.ADMIN: "order_pages:dashboard",
        }
        route_name = destinations.get(profile.role, "home")
        return reverse(route_name)


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = CustomerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your customer account is ready.")
        return redirect("home")
    return render(request, "accounts/register.html", {"form": form})
