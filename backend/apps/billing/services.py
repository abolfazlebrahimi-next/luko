"""
منطقِ اشتراک و پرداخت — تنها جایی که وضعیتِ پرداخت عوض می‌شود.

دو درگاه: زیبال (پیش‌فرض) و وندار (settings.PAYMENT_GATEWAY). هر پرداخت درگاهِ خودش را در
`Payment.gateway` نگه می‌دارد و بازگشت، تأیید و پیگیری همیشه با همان است؛ پس عوض کردنِ درگاه
پرداخت‌های نیمه‌کاره‌ی قبلی را خراب نمی‌کند.

چرخه‌ی یک پرداخت (وندار؛ زیبال همین است با request/verify/inquiry، پایینِ همین فایل):

    start_checkout   ردیفِ pending + توکنِ درگاه → آدرسِ درگاه
    handle_callback  بازگشتِ مرورگر از درگاه → settle
    settle           verify؛ اگر پاسخِ verify گم شده بود (دومی خطا می‌دهد)، transaction
                     با code=2 نشان می‌دهد که پول تأیید شده → activate
    reconcile        کارِ زمان‌بندی‌شده: پرداختی که مرورگرش برنگشت (بسته شد، اینترنت قطع شد)
                     با transaction پیگیری و در صورتِ لزوم تأیید می‌شود

قفل‌ها: هر تغییرِ وضعیت داخلِ `select_for_update` روی همان پرداخت است، پس بازگشتِ
دوباره از درگاه یا هم‌زمانیِ بازگشت و reconcile پرداخت را دوبار ثبت نمی‌کند؛ فعال‌سازی
روی ردیفِ خودِ بچه هم قفل می‌گیرد تا دو خریدِ هم‌زمان دوره‌ها را روی هم نیندازند.
پول فقط وقتی «پرداخت‌شده» است که درگاه بگوید تأیید شده **و** مبلغ همان باشد که ما خواستیم.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.accounts.models import User

from . import bazaar, vandar, zibal
from .models import Payment, Plan

log = logging.getLogger("luko.billing")

DAY = timedelta(days=1)
#: یادآوریِ تمدید از چند روز پیش از پایان
EXPIRY_NOTICE_DAYS = 7
#: پرداختی که مرورگرش برنگشته، پیش از این‌که reconcile سراغش برود (کاربر هنوز در درگاه است)
RECONCILE_AFTER = timedelta(minutes=2)
#: وندار تا ۲۰ دقیقه بعد از رفتن به درگاه تأیید می‌پذیرد؛ با کمی حاشیه
GATEWAY_WINDOW = timedelta(minutes=25)
#: سقفِ پرداختِ نیمه‌کاره‌ی هم‌زمانِ یک والد (جلوی ساختنِ انبوهِ تراکنش را می‌گیرد)
MAX_PENDING_PER_HOUR = 10

_MOBILE = re.compile(r"^09\d{9}$")


class CheckoutError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# ------------------------------------------------------------------ وضعیت
@dataclass
class Subscription:
    active: bool
    plan: Payment | None          # دوره‌ای که همین حالا جاری است
    ends_at: datetime | None      # پایانِ کلِ اشتراکِ پرداخت‌شده (با دوره‌های پشتِ‌سرِ هم)
    chain_start: datetime | None  # شروعِ دوره‌ی جاری (برای نوارِ پیشرفت)
    days_left: int
    total_days: int
    last_paid: Payment | None     # آخرین خرید — مبنای صورت‌حسابِ تمدید
    #: اشتراکِ همیشگی (ادمین‌ها و گروهِ «اشتراکِ همیشگی») — بی‌تاریخِ پایان، بی‌تمدید، بی‌یادآوری
    lifetime: bool = False
    #: دوره‌ی آخر اشتراکِ کافه‌بازار است که خودکار تمدید می‌شود — نه یادآوری، نه صورت‌حسابِ تمدید
    auto_renews: bool = False

    @property
    def expiring_soon(self) -> bool:
        return self.active and not self.lifetime and not self.auto_renews and self.days_left <= EXPIRY_NOTICE_DAYS


# ------------------------------------------------------------------ اشتراکِ همیشگی
#: حساب‌های نمایشی و بازبینی که همیشه اشتراکِ کامل دارند؛ عضویت از پنلِ جنگو (کاربر ← گروه‌ها).
#: عضویت در این گروه دسترسیِ ادمین نمی‌دهد (is_staff جداست).
LIFETIME_GROUP = "اشتراکِ همیشگی"
ADMIN_Q = Q(is_superuser=True) | Q(is_staff=True) | Q(role=User.Role.TEAM_ADMIN)


def lifetime_access(child: User) -> bool:
    """
    آیا این فرزند همیشه اشتراکِ کامل دارد؟ بله اگر خودش یا یکی از والدهای وصلش ادمین است، شماره‌اش
    شماره‌ی یک حسابِ ادمین است (حسابِ والد/کودکِ خودِ ادمین‌ها نقشِ جدا دارد)، یا عضوِ گروهِ «اشتراکِ همیشگی» است.
    """
    from apps.parent.models import ParentChild

    parents = ParentChild.objects.filter(child=child, is_active=True).values("parent_id")
    accounts = User.objects.filter(Q(pk=child.pk) | Q(pk__in=parents))
    if accounts.filter(ADMIN_Q).exists() or accounts.filter(groups__name=LIFETIME_GROUP).exists():
        return True
    return User.objects.filter(phone__in=accounts.values("phone")).filter(ADMIN_Q).exists()


def subscription(child: User, now: datetime | None = None) -> Subscription:
    now = now or timezone.now()
    paid = list(Payment.objects.filter(child=child, status=Payment.Status.PAID,
                                       ends_at__isnull=False).select_related("plan"))
    last_paid = max(paid, key=lambda p: p.paid_at or p.created_at, default=None)
    if lifetime_access(child):
        return Subscription(True, None, None, None, 0, 0, last_paid, lifetime=True)
    future = [p for p in paid if p.ends_at > now]
    if not future:
        return Subscription(False, None, None, None, 0, 0, last_paid)
    ends_at = max(p.ends_at for p in future)
    current = next((p for p in sorted(future, key=lambda p: p.starts_at) if p.starts_at <= now), None)
    current = current or min(future, key=lambda p: p.starts_at)
    chain_start = min(current.starts_at, now)
    days_left = max(1, math.ceil((ends_at - now) / DAY))
    total_days = max(days_left, math.ceil((ends_at - chain_start) / DAY))
    last = max(future, key=lambda p: p.ends_at)
    auto_renews = last.gateway == Payment.Gateway.BAZAAR and bool(last.gateway_response.get("autoRenewing"))
    return Subscription(True, current, ends_at, chain_start, days_left, total_days, last_paid,
                        auto_renews=auto_renews)


def renewal_plan(sub: Subscription) -> Plan | None:
    """صورت‌حسابِ تمدید: همان پلنی که آخرین بار خریده شد (اگر هنوز فروخته می‌شود)."""
    if sub.last_paid is None:
        return None
    plan = sub.last_paid.plan
    return plan if plan.is_active else None


def linked_children(parent: User):
    from apps.parent.models import ParentChild

    return [link.child for link in ParentChild.objects.filter(parent=parent, is_active=True)
            .select_related("child").order_by("created_at")]


def is_linked(parent: User, child_id) -> User | None:
    from apps.parent.models import ParentChild

    link = ParentChild.objects.filter(parent=parent, child_id=child_id, is_active=True) \
        .select_related("child").first()
    return link.child if link else None


def child_name(child: User | None) -> str:
    if child is None:
        return ""
    return f"{child.first_name} {child.last_name}".strip() or child.phone


# ------------------------------------------------------------------ پرداخت
GATEWAY_ERRORS = (vandar.VandarError, zibal.ZibalError)


def active_gateway() -> str:
    """درگاهِ پرداخت‌های تازه؛ مقدارِ ناشناخته یعنی زیبال"""
    gateway = (settings.PAYMENT_GATEWAY or "").strip().lower()
    # کافه‌بازار درگاهِ سایت نیست؛ خریدش فقط از داخلِ اپ و با verify_bazaar_purchase است
    return gateway if gateway in (Payment.Gateway.ZIBAL, Payment.Gateway.VANDAR) else Payment.Gateway.ZIBAL


def callback_url(gateway: str = Payment.Gateway.VANDAR) -> str:
    if gateway == Payment.Gateway.ZIBAL:
        # زیبال callbackUrl را فقط روی دامنه‌ی ثبت‌شده‌ی درگاه می‌پذیرد (کدِ ۱۰۶)
        return settings.ZIBAL_SITE_URL.rstrip("/") + "/api/v1/billing/callback/zibal"
    return settings.SITE_URL.rstrip("/") + "/api/v1/billing/callback"


def pay_url(payment: Payment) -> str:
    """
    جایی که مرورگرِ والد به آن می‌رود. زیبال صفحه‌ی پرداخت را فقط با Refererِ دامنه‌ی ثبت‌شده باز می‌کند
    (my.luko.ir ← «دامنه غیرمجاز»؛ آزمونِ ۲۴ مهر)، پس اول به صفحه‌ی گذرِ کوچکی روی همان دامنه می‌رود.
    """
    if payment.gateway == Payment.Gateway.ZIBAL:
        return settings.ZIBAL_SITE_URL.rstrip("/") + f"/api/v1/billing/zibal/go/{payment.token}"
    return vandar.pay_url(payment.token)


def return_hosts() -> set[str]:
    """دامنه‌هایی که پنلِ والدین رویشان است و بازگشت از درگاه به آن‌ها مجاز است"""
    return {urlparse(url).netloc for url in (settings.SITE_URL, settings.ZIBAL_SITE_URL) if url}


def result_url(payment: Payment | None, problem: str = "") -> str:
    site = settings.SITE_URL.rstrip("/")
    if payment is not None and payment.return_host in return_hosts():
        site = f"{urlparse(settings.SITE_URL).scheme or 'https'}://{payment.return_host}"
    base = site + "/parent-panel/subscription/result"
    if payment is None:
        return f"{base}?error={problem or 'unknown'}"
    return f"{base}?payment={payment.id}"


def _factor_number() -> str:
    return f"LK{timezone.localtime():%y%m%d}{secrets.randbelow(10**6):06d}"


def start_checkout(parent: User, child: User, plan: Plan, *, host: str = "") -> Payment:
    if not plan.is_active:
        raise CheckoutError("این پلن دیگر فروخته نمی‌شود.")
    if lifetime_access(child):
        # پولی برای چیزی که همین حالا همیشگی است گرفته نشود
        raise CheckoutError("این فرزند اشتراکِ همیشگی دارد و خرید لازم نیست.")
    recent = Payment.objects.filter(payer=parent, status=Payment.Status.PENDING,
                                    created_at__gte=timezone.now() - timedelta(hours=1)).count()
    if recent >= MAX_PENDING_PER_HOUR:
        raise CheckoutError("چند پرداختِ نیمه‌کاره دارید؛ چند دقیقه‌ی دیگر دوباره تلاش کنید.", 429)

    name = child_name(child)
    gateway = active_gateway()
    for _ in range(5):
        try:
            payment = Payment.objects.create(
                payer=parent, child=child, plan=plan, plan_title=plan.title, gateway=gateway,
                return_host=host if host in return_hosts() else "",
                duration_days=plan.duration_days, amount_toman=plan.price_toman,
                amount_rial=plan.price_rial, payer_phone=parent.phone, child_name=name,
                factor_number=_factor_number(),
            )
            break
        except IntegrityError:          # شماره‌ی فاکتورِ تکراری؛ بسیار نادر
            continue
    else:
        raise CheckoutError("ساختِ صورت‌حساب انجام نشد؛ دوباره تلاش کنید.", 500)

    description = f"اشتراکِ {plan.title} لوکو برای {name}"
    mobile = parent.phone if _MOBILE.match(parent.phone or "") else ""
    try:
        if gateway == Payment.Gateway.ZIBAL:
            token = zibal.request(amount_rial=payment.amount_rial, callback_url=callback_url(gateway),
                                  order_id=payment.factor_number, description=description, mobile=mobile)
        else:
            token = vandar.send(amount_rial=payment.amount_rial, callback_url=callback_url(gateway),
                                factor_number=payment.factor_number, description=description, mobile=mobile)
    except GATEWAY_ERRORS as exc:
        log.warning("checkout %s (%s): request failed: %s", payment.factor_number, gateway, exc.message)
        Payment.objects.filter(pk=payment.pk).update(status=Payment.Status.FAILED,
                                                     message=exc.message[:255])
        raise CheckoutError(
            "درگاهِ پرداخت الان در دسترس نیست؛ چند دقیقه‌ی دیگر دوباره تلاش کنید."
            if exc.transient else "درگاهِ پرداخت درخواست را نپذیرفت؛ با پشتیبانی تماس بگیرید.",
            503 if exc.transient else 502,
        ) from exc
    payment.token = token
    payment.save(update_fields=["token", "updated_at"])
    return payment


def _amount_matches(payment: Payment, data: dict) -> bool:
    try:
        return round(float(data.get("amount"))) == payment.amount_rial
    except (TypeError, ValueError):
        return False


def _mark(payment: Payment, status: str, message: str, data: dict | None = None) -> None:
    payment.status = status
    payment.message = message[:255]
    if data:
        payment.gateway_response = data
    payment.save(update_fields=["status", "message", "gateway_response", "updated_at"])


def _activate(payment: Payment, data: dict) -> None:
    """پرداختِ تأییدشده → دوره‌ی اشتراک (پشتِ دوره‌ی جاری، اگر هست)."""
    now = timezone.now()
    if payment.child_id:
        # دو خریدِ هم‌زمان برای یک بچه نباید هر دو «از همین حالا» شروع شوند
        User.objects.select_for_update().filter(pk=payment.child_id).first()
    current_end = Payment.objects.filter(
        child_id=payment.child_id, status=Payment.Status.PAID, ends_at__gt=now,
    ).exclude(pk=payment.pk).aggregate(end=Max("ends_at"))["end"]
    start = max(now, current_end) if current_end else now
    payment.status = Payment.Status.PAID
    payment.paid_at = now
    payment.starts_at = start
    payment.ends_at = start + timedelta(days=payment.duration_days)
    payment.trans_id = str(data.get("transId") or "")[:40]
    payment.card_number = str(data.get("cardNumber") or "")[:32]
    payment.message = str(data.get("message") or "پرداخت تأیید شد")[:255]
    payment.gateway_response = data
    payment.save()
    log.info("payment %s paid: %s rial, child %s until %s", payment.factor_number,
             payment.amount_rial, payment.child_id, payment.ends_at)
    # همان تراکنش: اگر ثبتِ پرداخت برگردد، اعلانِ «فعال شد» هم برمی‌گردد
    from .notices import payment_succeeded

    payment_succeeded(payment)
    from apps.parent.referrals import reward_purchase
    reward_purchase(payment)


def settle(payment: Payment) -> None:
    """
    پرداختِ pending را با وندار تمام می‌کند. باید داخلِ تراکنش و با قفل روی
    همان ردیف صدا زده شود. خطای موقتِ شبکه پرداخت را pending نگه می‌دارد تا
    reconcile دوباره سراغش برود — هیچ‌وقت به‌خاطرِ قطعیِ شبکه «ناموفق» نمی‌شود.
    """
    if payment.status != Payment.Status.PENDING or not payment.token:
        return
    if payment.gateway == Payment.Gateway.ZIBAL:
        _zibal_settle(payment)
        return
    payment.verify_attempts += 1
    payment.save(update_fields=["verify_attempts", "updated_at"])
    try:
        data = vandar.verify(payment.token)
    except vandar.VandarError as exc:
        if exc.transient:
            return
        data = None
        verify_error = exc
    else:
        verify_error = None
    if data is not None:
        if _amount_matches(payment, data):
            _activate(payment, data)
        else:
            log.error("payment %s: AMOUNT MISMATCH verify=%s expected=%s", payment.factor_number,
                      data.get("amount"), payment.amount_rial)
            _mark(payment, Payment.Status.FAILED, "مبلغِ تأییدشده با صورت‌حساب نمی‌خواند", data)
        return

    # verify رد کرد: یا پرداخت نشده، یا قبلاً تأیید شده و پاسخش به ما نرسیده بود
    try:
        info = vandar.transaction(payment.token)
    except vandar.VandarError as exc:
        if exc.transient:
            return
        info = exc.data
    code = info.get("code") if isinstance(info, dict) else None
    if code == vandar.CODE_CONFIRMED and _amount_matches(payment, info):
        _activate(payment, info)
    elif code == vandar.CODE_AWAITING and timezone.now() - payment.created_at < GATEWAY_WINDOW:
        return        # هنوز در مهلتِ درگاه؛ دورِ بعد
    elif code == vandar.CODE_EXPIRED or code == vandar.CODE_AWAITING:
        _mark(payment, Payment.Status.EXPIRED, "مهلتِ پرداخت تمام شد", info)
    else:
        _mark(payment, Payment.Status.FAILED,
              (verify_error.message if verify_error else "") or "پرداخت انجام نشد", info or {})


def _settle_failed_return(payment: Payment) -> None:
    """
    بانک «ناموفق» برگرداند (لغو، موجودیِ ناکافی، رمزِ غلط…). اگر وندار با این
    حال پول را تأییدشده یا منتظرِ تأیید می‌داند، همین حالا یک‌بار تأیید می‌کنیم؛
    وگرنه پرداخت فوراً «ناموفق» است — والدی که لغو کرده نباید پشتِ «در حالِ بررسی» بماند.
    """
    try:
        info = vandar.transaction(payment.token)
    except vandar.VandarError as exc:
        info = exc.data if not exc.transient else {}
    code = info.get("code") if isinstance(info, dict) else None
    if code == vandar.CODE_CONFIRMED and _amount_matches(payment, info):
        _activate(payment, info)
        return
    if code == vandar.CODE_AWAITING:
        try:
            data = vandar.verify(payment.token)
        except vandar.VandarError as exc:
            if exc.transient:
                return          # شبکه قطع شد؛ reconcile ادامه می‌دهد
        else:
            if _amount_matches(payment, data):
                _activate(payment, data)
                return
    _mark(payment, Payment.Status.FAILED, "پرداخت انجام نشد یا لغو شد", info or {})


def handle_callback(token: str, payment_status: str) -> Payment | None:
    """بازگشتِ مرورگر از وندار. چندبار صدا زدنش بی‌خطر است."""
    if not token:
        return None
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(token=token, gateway=Payment.Gateway.VANDAR).first()
        if payment is None:
            log.warning("callback for unknown token")
            return None
        if payment.status != Payment.Status.PENDING:
            return payment
        if payment_status == "OK":
            settle(payment)
        else:
            _settle_failed_return(payment)
    payment.refresh_from_db()
    return payment


def reconcile(payment_id: int) -> Payment | None:
    """پیگیریِ یک پرداختِ pending (کارِ زمان‌بندی‌شده و صفحه‌ی نتیجه)."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(pk=payment_id).first()
        if payment is None or payment.status != Payment.Status.PENDING:
            return payment
        age = timezone.now() - payment.created_at
        if not payment.token:
            if age > timedelta(minutes=10):
                _mark(payment, Payment.Status.FAILED, "ساختِ پرداخت ناتمام ماند")
            return payment
        if age < RECONCILE_AFTER:
            return payment
        if payment.gateway == Payment.Gateway.ZIBAL:
            _zibal_reconcile(payment, age)
            payment.refresh_from_db()
            return payment
        try:
            info = vandar.transaction(payment.token)
        except vandar.VandarError as exc:
            if exc.transient:
                return payment
            info = exc.data
        code = info.get("code") if isinstance(info, dict) else None
        if code in (vandar.CODE_AWAITING, vandar.CODE_CONFIRMED):
            if code == vandar.CODE_CONFIRMED and _amount_matches(payment, info):
                _activate(payment, info)
            else:
                settle(payment)
        elif code == vandar.CODE_EXPIRED or (code is None and age > timedelta(hours=2)):
            _mark(payment, Payment.Status.EXPIRED, "مهلتِ پرداخت تمام شد", info or {})
        elif code in (vandar.CODE_WRONG, vandar.CODE_FAILED):
            # «پرداخت‌نشده» در مهلتِ درگاه یعنی کاربر هنوز روی صفحه‌ی بانک است
            if age > GATEWAY_WINDOW:
                _mark(payment, Payment.Status.FAILED, "پرداخت انجام نشد", info)
    payment.refresh_from_db()
    return payment


# ------------------------------------------------------------------ زیبال
def _zibal_normal(data: dict) -> dict:
    """پاسخِ زیبال به شکلی که _activate می‌خواند (شماره‌ی مرجع، کارت) + خودِ پاسخ"""
    return {**data, "transId": data.get("refNumber") or "", "cardNumber": data.get("cardNumber") or "",
            "message": "پرداخت تأیید شد"}


def _zibal_paid(payment: Payment, data: dict) -> None:
    if _amount_matches(payment, data):
        _activate(payment, _zibal_normal(data))
    else:
        log.error("payment %s: AMOUNT MISMATCH zibal=%s expected=%s", payment.factor_number,
                  data.get("amount"), payment.amount_rial)
        _mark(payment, Payment.Status.FAILED, "مبلغِ تأییدشده با صورت‌حساب نمی‌خواند", data)


def _zibal_inquiry(payment: Payment) -> dict | None:
    """وضعیتِ پرداخت از زیبال؛ None یعنی شبکه/درگاه موقتاً جواب نداد (pending می‌ماند)."""
    try:
        return zibal.inquiry(payment.token)
    except zibal.ZibalError as exc:
        if exc.transient:
            return None
        return {**exc.data, "status": None}


def _zibal_apply(payment: Payment, info: dict, *, allow_verify: bool) -> None:
    """تصمیم از روی inquiry. `allow_verify`: «پرداخت‌شده، تأییدنشده» را همین حالا تأیید کن."""
    status = info.get("status")
    in_window = timezone.now() - payment.created_at < GATEWAY_WINDOW
    if status == zibal.STATUS_VERIFIED:
        _zibal_paid(payment, info)
    elif status == zibal.STATUS_PAID_UNVERIFIED and allow_verify:
        _zibal_settle(payment)
    elif status in (zibal.STATUS_PENDING, zibal.STATUS_PAID_UNVERIFIED) and in_window:
        return          # هنوز در درگاه یا در مهلتِ تأیید؛ دورِ بعدِ reconcile
    elif status == zibal.STATUS_PAID_UNVERIFIED:
        # زیبال پولِ تأییدنشده را بعد از ۲۰ دقیقه به کارت برمی‌گرداند
        _mark(payment, Payment.Status.FAILED, "پرداخت تأیید نشد؛ مبلغ به کارتِ شما برمی‌گردد", info)
    elif status == zibal.STATUS_PENDING:
        _mark(payment, Payment.Status.EXPIRED, "مهلتِ پرداخت تمام شد", info)
    else:
        _mark(payment, Payment.Status.FAILED,
              zibal.status_message(status) if status is not None else "پرداخت انجام نشد", info)


def _zibal_settle(payment: Payment) -> None:
    """
    تأییدِ پرداختِ زیبال (داخلِ تراکنش و با قفل). verify ۱۰۰ یعنی همین حالا تأیید شد؛ ۲۰۱ یعنی پیش‌تر تأیید شده
    بود و پاسخش به ما نرسیده بود — آن‌وقت inquiry مبلغ و شماره‌ی مرجع را می‌دهد. verifyِ ردشده (پرداخت نشده،
    لغو) هم با inquiry روشن می‌شود. خطای شبکه پرداخت را pending نگه می‌دارد تا reconcile دوباره بیاید.
    """
    payment.verify_attempts += 1
    payment.save(update_fields=["verify_attempts", "updated_at"])
    try:
        data = zibal.verify(payment.token)
    except zibal.ZibalError as exc:
        if exc.transient:
            return
        info = _zibal_inquiry(payment)
        if info is not None:
            _zibal_apply(payment, info, allow_verify=False)
        return
    if data.get("result") == zibal.RESULT_ALREADY_VERIFIED or data.get("amount") is None:
        info = _zibal_inquiry(payment)
        if info is not None:
            _zibal_apply(payment, info, allow_verify=False)
        return
    _zibal_paid(payment, data)


def handle_zibal_callback(track_id: str, success: str) -> Payment | None:
    """
    بازگشتِ مرورگر از زیبال (?trackId=…&success=1|0). به `success` و `status`ِ مرورگر اعتماد نمی‌شود؛ فقط
    مسیر را انتخاب می‌کند: «موفق» → verify، «ناموفق» → inquiry (لغوِ والد همان لحظه «ناموفق» می‌شود).
    چندبار صدا زدنش بی‌خطر است.
    """
    if not track_id:
        return None
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(token=track_id, gateway=Payment.Gateway.ZIBAL).first()
        if payment is None:
            log.warning("zibal callback for unknown trackId")
            return None
        if payment.status != Payment.Status.PENDING:
            return payment
        if success == "1":
            _zibal_settle(payment)
        else:
            info = _zibal_inquiry(payment)
            if info is not None:
                _zibal_apply(payment, info, allow_verify=True)
    payment.refresh_from_db()
    return payment


def _zibal_reconcile(payment: Payment, age: timedelta) -> None:
    info = _zibal_inquiry(payment)
    if info is None:
        return
    if info.get("status") is None and age < timedelta(hours=2):
        return          # شناسه را نشناخت؛ شاید زیبال هنوز ثبتش نکرده
    _zibal_apply(payment, info, allow_verify=True)


# ------------------------------------------------------------------ کافه‌بازار
#: توکنِ خریدِ بازار تا ۱۰۰۰ نویسه است؛ ستونِ token فقط ۱۲۸ — اثرِ انگشتش یکتا می‌ماند و خودِ توکن در gateway_response
BAZAAR_TOKEN_MAX = 1000


def bazaar_key(purchase_token: str) -> str:
    return "bz:" + hashlib.sha256(purchase_token.encode()).hexdigest()


def _bazaar_check(sku: str, purchase_token: str) -> bazaar.BazaarSubscription:
    try:
        return bazaar.subscription_status(sku, purchase_token)
    except bazaar.BazaarError as exc:
        log.warning("bazaar verify %s: %s", sku, exc.message)
        if exc.transient:
            raise CheckoutError("کافه‌بازار الان جواب نمی‌دهد؛ چند دقیقه‌ی دیگر دوباره تلاش کنید.", 503) from exc
        raise CheckoutError("کافه‌بازار این خرید را تأیید نکرد.", 400) from exc


def _bazaar_extend(payment: Payment, sub: bazaar.BazaarSubscription) -> bool:
    """تمدیدِ خودکار یا لغوِ تمدید در بازار → همان ردیف. True اگر چیزی عوض شد."""
    data = {**payment.gateway_response, "autoRenewing": sub.auto_renewing, "bazaar": sub.raw}
    changed = data != payment.gateway_response
    payment.gateway_response = data
    if sub.valid_until > payment.ends_at:
        payment.ends_at = sub.valid_until
        changed = True
    if changed:
        payment.save(update_fields=["gateway_response", "ends_at", "updated_at"])
    return changed


def verify_bazaar_purchase(parent: User, child: User, plan: Plan, purchase_token: str,
                           order_id: str = "") -> Payment:
    """
    خریدِ اشتراکی که اپِ اندروید با Poolakey از کافه‌بازار کرد → دوره‌ی اشتراک. فقط حرفِ خودِ بازار ملاک است
    (توکن + SKUِ همین پلن)؛ دوره همان بازه‌ای است که بازار می‌گوید (شروعِ خرید تا validUntil)، چون تمدیدش را هم
    بازار انجام می‌دهد. چندبار فرستادنِ یک توکن بی‌خطر است (بازیابیِ خرید، تمدید)؛ هر توکن فقط مالِ یک فرزند است.
    """
    purchase_token = (purchase_token or "").strip()
    if not purchase_token or len(purchase_token) > BAZAAR_TOKEN_MAX:
        raise CheckoutError("شناسه‌ی خرید نامعتبر است.")
    sku = bazaar.sku_for(plan.code)
    key = bazaar_key(purchase_token)
    existing = Payment.objects.filter(token=key).first()
    if existing is not None and existing.child_id != child.pk:
        raise CheckoutError("این خرید پیش‌تر برای فرزندِ دیگری ثبت شده است.", 409)
    # خریدِ تازه فقط برای پلنِ فروشی؛ بازیابیِ خریدِ قبلی حتی اگر پلن بعداً از فروش افتاده باشد
    if existing is None and (not plan.is_active or not sku):
        raise CheckoutError("این پلن در کافه‌بازار فروخته نمی‌شود.")
    if existing is None and lifetime_access(child):
        raise CheckoutError("این فرزند اشتراکِ همیشگی دارد و خرید لازم نیست.")
    sub = _bazaar_check(existing.gateway_response.get("sku", sku) if existing else sku, purchase_token)
    if existing is not None:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=existing.pk)
            _bazaar_extend(payment, sub)
        return payment

    now = timezone.now()
    if sub.valid_until <= now:
        raise CheckoutError("این اشتراک در کافه‌بازار تمام شده است.")
    response = {"sku": sku, "purchaseToken": purchase_token, "orderId": str(order_id or "")[:64],
                "autoRenewing": sub.auto_renewing, "bazaar": sub.raw}
    try:
        with transaction.atomic():
            User.objects.select_for_update().filter(pk=child.pk).first()
            payment = Payment.objects.create(
                payer=parent, child=child, plan=plan, plan_title=plan.title, gateway=Payment.Gateway.BAZAAR,
                duration_days=plan.duration_days, amount_toman=plan.price_toman, amount_rial=plan.price_rial,
                payer_phone=parent.phone, child_name=child_name(child),
                factor_number=f"BZ{timezone.localtime():%y%m%d}{secrets.randbelow(10**6):06d}",
                token=key, trans_id=str(order_id or "")[:40], status=Payment.Status.PAID,
                message="خرید از کافه‌بازار", gateway_response=response,
                paid_at=now, starts_at=min(sub.started_at, now), ends_at=sub.valid_until,
            )
            from .notices import payment_succeeded

            payment_succeeded(payment)
            from apps.parent.referrals import reward_purchase
            reward_purchase(payment)
    except IntegrityError:
        # همین توکن هم‌زمان از درخواستِ دیگری ثبت شد (یا شماره‌ی فاکتورِ تکراری؛ بسیار نادر)
        payment = Payment.objects.filter(token=key, child=child).first()
        if payment is None:
            raise CheckoutError("ثبتِ خرید انجام نشد؛ دوباره تلاش کنید.", 500)
        return payment
    log.info("bazaar %s paid: child %s until %s", payment.factor_number, child.pk, payment.ends_at)
    return payment


def refresh_bazaar(payment_id: int) -> Payment | None:
    """وضعیتِ تازه‌ی یک اشتراکِ بازار (کارِ زمان‌بندی‌شده): تمدیدِ خودکار ends_at را جلو می‌برد."""
    payment = Payment.objects.filter(pk=payment_id, gateway=Payment.Gateway.BAZAAR,
                                     status=Payment.Status.PAID).first()
    token = payment.gateway_response.get("purchaseToken") if payment else None
    if not token:
        return payment
    try:
        sub = bazaar.subscription_status(payment.gateway_response.get("sku", ""), token)
    except bazaar.BazaarError as exc:
        log.warning("bazaar refresh %s: %s", payment.factor_number, exc.message)
        return payment
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        _bazaar_extend(payment, sub)
    return payment


# ------------------------------------------------------------------ هدیه
GIFT_MAX_DAYS = 730


def gift_subscription(*, child: User, days: int, granted_by: User, note: str = "") -> Payment:
    """
    چند روز اشتراکِ هدیه از داشبورد (پشتیبانی، جبرانِ مشکل، تخفیف). مثلِ خرید پشتِ
    دوره‌ی جاری می‌نشیند و در صورت‌حسابِ والد با برچسبِ «هدیه» دیده می‌شود.
    """
    if child.role != User.Role.STUDENT:
        raise CheckoutError("اشتراک فقط برای حسابِ دانش‌آموز است.")
    if not (1 <= int(days) <= GIFT_MAX_DAYS):
        raise CheckoutError(f"مدتِ هدیه باید بینِ ۱ تا {GIFT_MAX_DAYS} روز باشد.")
    plan = Plan.objects.order_by("duration_days").first()
    if plan is None:
        raise CheckoutError("هیچ پلنی تعریف نشده است.", 500)
    with transaction.atomic():
        User.objects.select_for_update().filter(pk=child.pk).first()
        now = timezone.now()
        current_end = Payment.objects.filter(child=child, status=Payment.Status.PAID, ends_at__gt=now) \
            .aggregate(end=Max("ends_at"))["end"]
        start = max(now, current_end) if current_end else now
        payment = Payment.objects.create(
            payer=None, child=child, plan=plan, plan_title=f"هدیه · {int(days)} روز"[:40],
            duration_days=int(days), amount_toman=0, amount_rial=0, child_name=child_name(child),
            status=Payment.Status.PAID, factor_number=f"GF{timezone.localtime():%y%m%d}{secrets.randbelow(10**6):06d}",
            source=Payment.Source.GIFT, granted_by=granted_by, note=(note or "")[:200],
            paid_at=now, starts_at=start, ends_at=start + timedelta(days=int(days)), message="اشتراکِ هدیه",
        )
        from .notices import gift_granted

        gift_granted(payment)
    log.info("gift %s: %s days for child %s by %s", payment.factor_number, days, child.pk, granted_by.pk)
    return payment


def revoke_gift(payment: Payment) -> Payment:
    """هدیه‌ی اشتباه را برمی‌دارد (فقط هدیه؛ پرداختِ واقعی هرگز)."""
    if payment.source != Payment.Source.GIFT:
        raise CheckoutError("فقط اشتراکِ هدیه لغوشدنی است.")
    payment.status = Payment.Status.EXPIRED
    payment.message = "هدیه لغو شد"
    payment.save(update_fields=["status", "message", "updated_at"])
    return payment
