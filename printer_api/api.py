from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import IsAdminRole, IsPrinter, IsStaffRole
from orders.models import PrintJob
from printer_api.serializers import (
    PendingLimitSerializer,
    PrintFailureSerializer,
    PrintJobSerializer,
    StaffPrintJobSerializer,
)
from printer_api.services import (
    PrintJobConflict,
    claim_print_job,
    list_pending_jobs,
    mark_failed,
    mark_printed,
    requeue_failed_job,
)


STAFF_OR_ADMIN = IsStaffRole | IsAdminRole


class PrintJobViewSet(viewsets.ViewSet):
    queryset = PrintJob.objects.none()
    serializer_class = PrintJobSerializer

    def get_permissions(self):
        permission = STAFF_OR_ADMIN if self.action == "requeue" else IsPrinter
        return [permission()]

    @action(detail=False, methods=("get",), url_path="pending")
    def pending(self, request):
        limit_serializer = PendingLimitSerializer(data=request.query_params)
        limit_serializer.is_valid(raise_exception=True)
        jobs = list_pending_jobs(limit_serializer.validated_data["limit"])
        results = PrintJobSerializer(jobs, many=True).data
        return Response({"count": len(results), "results": results})

    @action(detail=True, methods=("post",), url_path="claim")
    def claim(self, request, pk=None):
        get_object_or_404(PrintJob, pk=pk)
        try:
            job = claim_print_job(pk)
        except PrintJobConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(PrintJobSerializer(job).data)

    @action(detail=True, methods=("post",), url_path="printed")
    def printed(self, request, pk=None):
        get_object_or_404(PrintJob, pk=pk)
        try:
            job = mark_printed(pk)
        except PrintJobConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(PrintJobSerializer(job).data)

    @action(detail=True, methods=("post",), url_path="failed")
    def failed(self, request, pk=None):
        get_object_or_404(PrintJob, pk=pk)
        serializer = PrintFailureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            job = mark_failed(pk, serializer.validated_data["error"])
        except PrintJobConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(StaffPrintJobSerializer(job).data)

    @action(detail=True, methods=("post",), url_path="requeue")
    def requeue(self, request, pk=None):
        get_object_or_404(PrintJob, pk=pk)
        try:
            job = requeue_failed_job(pk)
        except PrintJobConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(StaffPrintJobSerializer(job).data)
