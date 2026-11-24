from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.serializers import DateTimeField

from accounts.permissions import IsAdminRole, IsCustomer, IsStaffRole
from orders.models import Order
from orders.serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderStatusHistorySerializer,
    OrderSummarySerializer,
)
from orders.services import InvalidOrderRequest, InvalidOrderTransition, StaleOrderStatus, place_order


ORDER_READERS = IsCustomer | IsStaffRole | IsAdminRole
STAFF_OR_ADMIN = IsStaffRole | IsAdminRole


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.none()
    http_method_names = ("get", "post", "head", "options")

    def get_permissions(self):
        if self.action in ("create", "mine", "cancel"):
            permission = IsCustomer
        elif self.action in ("list", "queue", "advance"):
            permission = STAFF_OR_ADMIN
        elif self.action == "history":
            permission = IsAdminRole
        else:
            permission = ORDER_READERS
        return [permission()]

    def get_queryset(self):
        queryset = Order.objects.select_related("customer").prefetch_related("items__menu_item")
        user = self.request.user
        if not user.is_superuser and not user.groups.filter(name__in=("Staff", "Admin")).exists():
            queryset = queryset.filter(customer=user)
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action in ("mine", "queue"):
            return OrderSummarySerializer
        return OrderDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = place_order(request.user, serializer.validated_data["items"])
        except InvalidOrderRequest as exc:
            raise ValidationError({"detail": str(exc)})
        order = Order.objects.select_related("customer").prefetch_related("items__menu_item").get(pk=order.pk)
        response_serializer = OrderDetailSerializer(order, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = OrderDetailSerializer(order, context=self.get_serializer_context())
        return Response(serializer.data)

    def _changed_since(self, queryset, request):
        value = request.query_params.get("since")
        if not value:
            return queryset
        try:
            since = DateTimeField(default_timezone=timezone.get_current_timezone()).run_validation(value)
        except ValidationError:
            raise ValidationError({"since": "Provide a valid ISO 8601 timestamp."})
        return queryset.filter(updated_at__gt=since)

    @action(detail=False, methods=("get",), url_path="mine")
    def mine(self, request):
        queryset = Order.objects.filter(customer=request.user).order_by("-created_at", "-pk")
        queryset = self._changed_since(queryset, request)
        page = self.paginate_queryset(queryset)
        serializer = OrderSummarySerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=("get",), url_path="queue")
    def queue(self, request):
        queryset = Order.objects.filter(
            status__in=(Order.Status.PLACED, Order.Status.PREPARING, Order.Status.READY)
        ).order_by("created_at", "pk")
        queryset = self._changed_since(queryset, request)
        page = self.paginate_queryset(queryset)
        serializer = OrderSummarySerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=("post",), url_path="cancel")
    def cancel(self, request, pk=None):
        order = self.get_queryset().filter(customer=request.user).filter(pk=pk).first()
        if order is None:
            from django.http import Http404

            raise Http404
        try:
            order.transition_to(Order.Status.CANCELLED, request.user)
        except StaleOrderStatus as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except InvalidOrderTransition as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=("post",), url_path="advance")
    def advance(self, request, pk=None):
        order = self.get_object()
        try:
            order.advance(request.user)
        except StaleOrderStatus as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except InvalidOrderTransition as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=("get",), url_path="history")
    def history(self, request, pk=None):
        order = Order.objects.filter(pk=pk).first()
        if order is None:
            from django.http import Http404

            raise Http404
        history = order.history.select_related("actor").all()
        serializer = OrderStatusHistorySerializer(history, many=True)
        return Response(serializer.data)
