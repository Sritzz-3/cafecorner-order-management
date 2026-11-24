from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import render

from menu.models import Category, MenuItem


@login_required
def browse_menu(request):
    available_items = MenuItem.objects.filter(is_available=True).order_by("name")
    categories = (
        Category.objects.filter(items__is_available=True)
        .distinct()
        .prefetch_related(Prefetch("items", queryset=available_items))
    )
    # Prefetch loads each category's available items in one query instead of one query per section.
    return render(request, "menu/browse.html", {"categories": categories})
