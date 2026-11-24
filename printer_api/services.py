from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from orders.models import Order, PrintJob


class PrintJobConflict(Exception):
    pass


def _job_queryset():
    return PrintJob.objects.select_related("order", "order__coupon").prefetch_related("order__items__menu_item")


@transaction.atomic
def list_pending_jobs(limit=10):
    now = timezone.now()
    cutoff = now - timedelta(seconds=settings.PRINT_CLAIM_TIMEOUT_SECONDS)
    # Expired leases return to the queue so a restarted Pi can see them again.
    PrintJob.objects.filter(status=PrintJob.Status.PRINTING, claimed_at__lt=cutoff).update(
        status=PrintJob.Status.PENDING,
        claimed_at=None,
        updated_at=now,
    )
    return _job_queryset().filter(status=PrintJob.Status.PENDING).order_by("created_at", "pk")[:limit]


@transaction.atomic
def claim_print_job(job_id):
    now = timezone.now()
    cutoff = now - timedelta(seconds=settings.PRINT_CLAIM_TIMEOUT_SECONDS)
    # A lease that expired between polling and claiming can be recovered here too.
    PrintJob.objects.filter(pk=job_id, status=PrintJob.Status.PRINTING, claimed_at__lt=cutoff).update(
        status=PrintJob.Status.PENDING,
        claimed_at=None,
        updated_at=now,
    )
    changed = PrintJob.objects.filter(pk=job_id, status=PrintJob.Status.PENDING).update(
        status=PrintJob.Status.PRINTING,
        claimed_at=now,
        updated_at=now,
    )
    if changed != 1:
        raise PrintJobConflict("This print job is no longer pending or its claim is still active.")
    return _job_queryset().get(pk=job_id)


@transaction.atomic
def mark_printed(job_id):
    now = timezone.now()
    changed = PrintJob.objects.filter(pk=job_id, status=PrintJob.Status.PRINTING).update(
        status=PrintJob.Status.PRINTED,
        printed_at=now,
        updated_at=now,
        claimed_at=None,
        last_error="",
    )
    if changed != 1:
        raise PrintJobConflict("Only a currently claimed print job can be marked printed.")
    return PrintJob.objects.get(pk=job_id)


@transaction.atomic
def mark_failed(job_id, error):
    job = PrintJob.objects.filter(pk=job_id, status=PrintJob.Status.PRINTING).values("retry_count").first()
    if job is None:
        raise PrintJobConflict("Only a currently claimed print job can be marked failed.")
    current_retry_count = job["retry_count"]
    new_retry_count = current_retry_count + 1
    next_status = (
        PrintJob.Status.FAILED if new_retry_count >= settings.PRINT_MAX_RETRIES else PrintJob.Status.PENDING
    )
    now = timezone.now()
    changed = PrintJob.objects.filter(
        pk=job_id,
        status=PrintJob.Status.PRINTING,
        retry_count=current_retry_count,
    ).update(
        status=next_status,
        retry_count=F("retry_count") + 1,
        last_error=error[:5000],
        claimed_at=None,
        updated_at=now,
    )
    if changed != 1:
        raise PrintJobConflict("This print job changed before the failure was recorded.")
    return PrintJob.objects.get(pk=job_id)


@transaction.atomic
def requeue_failed_job(job_id):
    now = timezone.now()
    changed = PrintJob.objects.filter(pk=job_id, status=PrintJob.Status.FAILED).update(
        status=PrintJob.Status.PENDING,
        retry_count=0,
        last_error="",
        claimed_at=None,
        printed_at=None,
        updated_at=now,
    )
    if changed != 1:
        raise PrintJobConflict("Only a failed print job can be re-queued.")
    return PrintJob.objects.get(pk=job_id)
