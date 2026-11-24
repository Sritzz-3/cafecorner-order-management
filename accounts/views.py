from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.forms import CustomerRegistrationForm


def home(request):
    return render(request, "accounts/home.html")


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
