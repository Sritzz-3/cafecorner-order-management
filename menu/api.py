from django.db.models import Prefetch
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.permissions import IsAdminRole, IsCustomer, IsStaffRole
from menu.models import Category, MenuItem
from menu.serializers import AvailabilitySerializer, CategorySerializer, MenuItemSerializer


MENU_READERS = IsCustomer | IsStaffRole | IsAdminRole


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_permissions(self):
        permission = MENU_READERS if self.action in ("list", "retrieve") else IsAdminRole
        return [permission()]

    def get_queryset(self):
        queryset = Category.objects.all()
        if not self.request.user.is_superuser and self.request.user.groups.filter(name="Customer").exists():
            queryset = queryset.filter(items__is_available=True).distinct()
        return queryset


class MenuItemViewSet(viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer

    def get_permissions(self):
        if self.action == "toggle_availability":
            permission = IsStaffRole | IsAdminRole
        elif self.action in ("list", "retrieve"):
            permission = MENU_READERS
        else:
            permission = IsAdminRole
        return [permission()]

    def get_queryset(self):
        queryset = MenuItem.objects.all()
        is_customer = (
            not self.request.user.is_superuser
            and self.request.user.groups.filter(name="Customer").exists()
        )
        if is_customer:
            queryset = queryset.filter(is_available=True)
        # select_related joins each item's category in the menu list, avoiding a category query per row.
        return queryset.select_related("category")

    def get_serializer_class(self):
        if self.action == "toggle_availability":
            return AvailabilitySerializer
        return MenuItemSerializer

    @action(detail=True, methods=("patch",), url_path="availability")
    def toggle_availability(self, request, pk=None):
        item = self.get_object()
        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MenuItemSerializer(item, context=self.get_serializer_context()).data)
