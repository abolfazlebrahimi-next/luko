"""
اشتراکِ هر فرزند و پرداخت‌هایش.

هر بچه به‌طورِ پیش‌فرض روی «رایگان» است (هیچ ردیفی لازم ندارد). هر پرداختِ
موفق یک دوره‌ی اشتراک است (`starts_at` تا `ends_at`)؛ خریدِ تازه وقتی اشتراکِ
قبلی هنوز باقی است، از پایانِ همان شروع می‌شود و روزهای باقی‌مانده نمی‌سوزد.
ردیفِ پرداخت هیچ‌وقت پاک نمی‌شود؛ حتی اگر حسابِ والد یا بچه پاک شود، با
نام و شماره‌ی ثبت‌شده در خودش برای حسابداری می‌ماند.
"""
from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Plan(TimeStampedModel):
    """پلنِ پولی؛ قیمت و مدت از پنلِ ادمین عوض می‌شوند."""

    code = models.SlugField(max_length=20, unique=True, verbose_name="کد")
    title = models.CharField(max_length=40, verbose_name="عنوان")
    duration_days = models.PositiveSmallIntegerField(verbose_name="مدت (روز)")
    price_toman = models.PositiveIntegerField(verbose_name="قیمت (تومان)")
    is_active = models.BooleanField(default=True, verbose_name="قابلِ خرید")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        verbose_name = "پلن اشتراک"
        verbose_name_plural = "پلن‌های اشتراک"
        ordering = ["order", "duration_days"]

    def __str__(self):
        return self.title

    @property
    def price_rial(self) -> int:
        return self.price_toman * 10


class Payment(TimeStampedModel):
    """یک بارِ رفتن به درگاه — هر وضعیتی که تمام شد (صورت‌حسابِ والد)."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "پرداخت‌شده"
        FAILED = "failed", "ناموفق"
        EXPIRED = "expired", "منقضی"

    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                              related_name="billing_payments", verbose_name="پرداخت‌کننده")
    child = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                              related_name="subscription_payments", verbose_name="فرزند")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payments",
                             verbose_name="پلن")
    # تصویرِ لحظه‌ی خرید: تغییرِ بعدیِ قیمت یا مدت در ادمین سابقه را عوض نکند
    plan_title = models.CharField(max_length=40, verbose_name="عنوانِ پلن")
    duration_days = models.PositiveSmallIntegerField(verbose_name="مدت (روز)")
    amount_toman = models.PositiveIntegerField(verbose_name="مبلغ (تومان)")
    amount_rial = models.PositiveBigIntegerField(verbose_name="مبلغ (ریال)")
    payer_phone = models.CharField(max_length=15, blank=True, verbose_name="شماره‌ی پرداخت‌کننده")
    child_name = models.CharField(max_length=120, blank=True, verbose_name="نامِ فرزند")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING,
                              db_index=True, verbose_name="وضعیت")
    class Gateway(models.TextChoices):
        VANDAR = "vandar", "وندار"
        ZIBAL = "zibal", "زیبال"
        BAZAAR = "bazaar", "کافه‌بازار"

    #: درگاهی که این پرداخت با آن ساخته شد؛ بازگشت، تأیید و پیگیری با همان است
    gateway = models.CharField(max_length=10, choices=Gateway.choices, default=Gateway.VANDAR,
                               verbose_name="درگاه")
    #: دامنه‌ای که والد پرداخت را از آن شروع کرد (my.luko.ir یا panel.luko.ir)؛ بعد از درگاه به همان برمی‌گردد،
    #: چون نشستِ ورودش فقط همان‌جاست
    return_host = models.CharField(max_length=64, blank=True, verbose_name="دامنه‌ی بازگشت")
    #: شماره‌ی فاکتورِ خودمان — به درگاه هم فرستاده می‌شود (orderIdِ زیبال، factorNumberِ وندار)
    factor_number = models.CharField(max_length=24, unique=True, verbose_name="شماره‌ی فاکتور")
    #: شناسه‌ی پرداخت در درگاه (توکنِ وندار یا trackIdِ زیبال)؛ بازگشت از درگاه با همین پیدا می‌شود
    token = models.CharField(max_length=128, unique=True, null=True, blank=True,
                             verbose_name="شناسه‌ی درگاه")
    trans_id = models.CharField(max_length=40, blank=True, verbose_name="شماره‌ی تراکنش")
    card_number = models.CharField(max_length=32, blank=True, verbose_name="کارت (پوشیده)")
    message = models.CharField(max_length=255, blank=True, verbose_name="پیامِ درگاه")
    gateway_response = models.JSONField(default=dict, blank=True, verbose_name="پاسخِ خامِ درگاه")
    verify_attempts = models.PositiveSmallIntegerField(default=0, verbose_name="تلاش‌های تأیید")

    class Source(models.TextChoices):
        GATEWAY = "gateway", "درگاه"
        GIFT = "gift", "هدیه"

    #: «هدیه» یعنی تیم از داشبورد داده؛ مبلغ صفر و بی‌درگاه
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.GATEWAY,
                              db_index=True, verbose_name="منبع")
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="granted_payments", verbose_name="هدیه‌دهنده")
    note = models.CharField(max_length=200, blank=True, verbose_name="یادداشت")

    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="زمانِ پرداخت")
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="شروعِ اشتراک")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="پایانِ اشتراک")

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["child", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.factor_number} · {self.plan_title} · {self.get_status_display()}"
