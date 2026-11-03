"""پیوندِ والد و فرزند — پایه‌ی همه‌ی گزارش‌های پنل والدین."""
from django.conf import settings
from django.db import models

from apps.common.constants import GRADE_CHOICES
from apps.common.models import TimeStampedModel


class ParentChild(TimeStampedModel):
    """
    یک والد می‌تواند چند فرزند داشته باشد و یک فرزند چند سرپرست
    (مثلاً پدر و مادر). دسترسیِ گزارش‌ها فقط از روی همین جدول داده می‌شود.
    """

    class Relation(models.TextChoices):
        PARENT = "parent", "والد"
        GUARDIAN = "guardian", "سرپرست"

    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="children_links", verbose_name="والد")
    child = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="parent_links", verbose_name="فرزند")
    relation = models.CharField(max_length=12, choices=Relation.choices,
                                default=Relation.PARENT, verbose_name="نسبت")
    grade = models.PositiveSmallIntegerField(default=1, choices=GRADE_CHOICES,
                                             verbose_name="پایه تحصیلی")
    school = models.CharField(max_length=120, blank=True, verbose_name="مدرسه")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "پیوند والد و فرزند"
        verbose_name_plural = "پیوندهای والد و فرزند"
        unique_together = ("parent", "child")
        indexes = [models.Index(fields=["parent", "is_active"])]

    def __str__(self):
        return f"{self.parent} → {self.child}"


class DailyAssignment(TimeStampedModel):
    """
    «بازی روزِ» انتخابی والد برای فرزند در یک تاریخ مشخص.
    برای هر بچه در هر روز فقط یک بازی — دوباره ثبت کردن، همان ردیف را عوض می‌کند.
    """

    child = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="daily_assignments", verbose_name="فرزند")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="assignments_made",
                                    verbose_name="انتخاب‌کننده")
    game_slug = models.SlugField(max_length=80, verbose_name="شناسه بازی")
    date = models.DateField(db_index=True, verbose_name="تاریخ")
    # پیام کوتاه والد به بچه
    note = models.CharField(max_length=160, blank=True, verbose_name="پیام والد")

    class Meta:
        verbose_name = "بازی روز"
        verbose_name_plural = "بازی‌های روز"
        unique_together = ("child", "date")
        ordering = ["-date"]
        indexes = [models.Index(fields=["child", "date"])]

    def __str__(self):
        return f"{self.child} @ {self.date} → {self.game_slug}"


class ParentPreference(TimeStampedModel):
    """تنظیم‌های حسابِ والد — چیزهایی که در تبِ «تنظیمات» سوییچ دارند."""

    parent = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="parent_preference", verbose_name="والد")
    weekly_report = models.BooleanField(default=True, verbose_name="اعلان گزارش هفتگی")
    activity_alerts = models.BooleanField(default=True, verbose_name="اعلان فعالیت")

    class Meta:
        verbose_name = "تنظیمات والد"
        verbose_name_plural = "تنظیمات والدین"

    def __str__(self):
        return f"تنظیمات {self.parent}"


class Notification(TimeStampedModel):
    """
    اعلانِ والد. ردیف‌ها از داده‌ی واقعی ساخته می‌شوند (نه دستی) و با
    `dedup_key` یکتا می‌مانند تا هر رویداد فقط یک‌بار اعلان بسازد.
    """

    class Kind(models.TextChoices):
        WEEKLY = "weekly", "گزارش هفتگی"
        GAMES = "games", "بازی‌های هفته"
        MOOD = "mood", "ثبت حال"
        IDLE = "idle", "بی‌فعالیتی"
        ASSIGNMENT = "assignment", "بازی روز"
        BILLING = "billing", "اشتراک و پرداخت"
        ANNOUNCEMENT = "announcement", "اطلاعیه"
        SUPPORT = "support", "پشتیبانی"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="parent_notifications", verbose_name="گیرنده")
    child = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              null=True, blank=True, related_name="about_notifications",
                              verbose_name="درباره فرزند")
    kind = models.CharField(max_length=12, choices=Kind.choices, verbose_name="نوع")
    title = models.CharField(max_length=160, verbose_name="عنوان")
    body = models.CharField(max_length=240, blank=True, verbose_name="متن")
    dedup_key = models.CharField(max_length=120, verbose_name="کلید یکتا")
    #: مسیرِ داخلِ پنل برای اقدام (مثلاً صورت‌حسابِ تمدید)؛ خالی یعنی فقط خبر
    link = models.CharField(max_length=200, blank=True, verbose_name="پیوند")
    is_read = models.BooleanField(default=False, verbose_name="خوانده شده")

    class Meta:
        verbose_name = "اعلان والد"
        verbose_name_plural = "اعلان‌های والد"
        ordering = ["-created_at"]
        unique_together = ("user", "dedup_key")
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.user} · {self.title}"


class ReferralCode(TimeStampedModel):
    parent = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_code")
    code = models.CharField(max_length=64, unique=True)


class Referral(TimeStampedModel):
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="referrals_sent")
    referred = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="referral_received")
    first_purchase = models.OneToOneField("billing.Payment", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(referrer=models.F("referred")), name="referral_not_self")]


class ReferralReward(TimeStampedModel):
    class Kind(models.TextChoices):
        REFERRER_JOIN = "referrer_join", "ثبت‌نام دوست"
        REFERRED_JOIN = "referred_join", "هدیه دعوت"
        PURCHASE = "purchase", "خرید دوست"

    referral = models.ForeignKey(Referral, on_delete=models.PROTECT, related_name="rewards")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="referral_rewards")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    days = models.PositiveSmallIntegerField()
    payment = models.OneToOneField("billing.Payment", null=True, blank=True, on_delete=models.PROTECT, related_name="referral_reward")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["referral", "kind"], name="unique_referral_reward_kind")]
