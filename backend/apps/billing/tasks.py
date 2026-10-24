"""کارهای زمان‌بندی‌شده‌ی پرداخت."""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Payment
from .services import EXPIRY_NOTICE_DAYS, RECONCILE_AFTER, reconcile


@shared_task
def reconcile_pending() -> int:
    """
    پرداختی که مرورگرش از درگاه برنگشت (بسته شد، اینترنت رفت) — بی‌این، پولِ
    کم‌شده بعد از ۲۰ دقیقه به خریدار برمی‌گشت و اشتراک هم فعال نمی‌شد.
    """
    now = timezone.now()
    ids = list(Payment.objects.filter(
        status=Payment.Status.PENDING, created_at__lte=now - RECONCILE_AFTER,
        created_at__gte=now - timedelta(days=2),
    ).values_list("id", flat=True)[:200])
    for pk in ids:
        reconcile(pk)
    # خیلی قدیمی‌ها دیگر پیگیری‌شدنی نیستند
    Payment.objects.filter(status=Payment.Status.PENDING, created_at__lt=now - timedelta(days=2)) \
        .update(status=Payment.Status.EXPIRED, message="مهلتِ پرداخت تمام شد")
    return len(ids)


@shared_task
def notify_expiring() -> int:
    """یادآوریِ تمدید برای همه‌ی والدها، حتی اگر این روزها پنل را باز نکرده‌اند."""
    from apps.parent.models import Notification, ParentChild

    from .notices import expiry_rows
    from .services import child_name

    now = timezone.now()
    window = timedelta(days=EXPIRY_NOTICE_DAYS)
    child_ids = set(Payment.objects.filter(
        status=Payment.Status.PAID, ends_at__gte=now - window, ends_at__lte=now + window,
    ).values_list("child_id", flat=True))
    rows = []
    for link in ParentChild.objects.filter(child_id__in=child_ids, is_active=True).select_related("parent", "child"):
        rows.extend(expiry_rows(link.parent, link.child, child_name(link.child), now))
    if rows:
        Notification.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


@shared_task
def refresh_bazaar_subscriptions() -> int:
    """
    اشتراکِ کافه‌بازار را خودِ بازار تمدید می‌کند؛ این‌جا نزدیکِ پایانِ هر دوره‌ی خودکار‌تمدیدشونده وضعیتش پرسیده
    می‌شود تا تمدید (یا لغوِ تمدید) به اشتراکِ بچه برسد. سقفِ APIِ بازار ۵۰ هزار درخواست در روز است.
    """
    from .services import refresh_bazaar

    now = timezone.now()
    ids = list(Payment.objects.filter(
        gateway=Payment.Gateway.BAZAAR, status=Payment.Status.PAID,
        ends_at__gte=now - timedelta(days=3), ends_at__lte=now + timedelta(days=EXPIRY_NOTICE_DAYS + 1),
        gateway_response__autoRenewing=True,
    ).values_list("id", flat=True)[:2000])
    for pk in ids:
        refresh_bazaar(pk)
    return len(ids)
