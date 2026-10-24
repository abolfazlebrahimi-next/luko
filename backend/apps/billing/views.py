"""
APIهای اشتراک — فقط والد، و فقط برای فرزندانِ خودش. بازگشت از درگاه تنها
مسیرِ بی‌احراز است (مرورگر از درگاه برمی‌گردد و توکنِ JWT همراهش نیست)؛ آن‌جا
هم هیچ چیز به گفته‌ی مرورگر اعتماد نمی‌شود — وضعیت را خودِ درگاه (زیبال یا وندار) تأیید می‌کند.
"""
from __future__ import annotations

from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.fa import fa_date, fa_time
from apps.parent.views import IsParent

from . import bazaar
from .models import Payment, Plan
from .services import (
    CheckoutError,
    child_name,
    handle_callback,
    handle_zibal_callback,
    is_linked,
    linked_children,
    pay_url,
    reconcile,
    renewal_plan,
    start_checkout,
    subscription,
    verify_bazaar_purchase,
)


def _fa_date(value):
    return fa_date(timezone.localtime(value).date(), with_year=True) if value else ""


def _fa_datetime(value):
    if not value:
        return ""
    local = timezone.localtime(value)
    return f"{fa_date(local.date(), with_year=True)} · {fa_time(local)}"


def _monthly_price() -> int | None:
    monthly = Plan.objects.filter(is_active=True, duration_days__lte=31).order_by("duration_days").first()
    return monthly.price_toman if monthly else None


def plan_payload(plan: Plan, monthly: int | None) -> dict:
    months = max(1, round(plan.duration_days / 30))
    saving = 0
    if monthly and months > 1:
        full = monthly * months
        saving = max(0, round(100 * (full - plan.price_toman) / full))
    return {
        "code": plan.code,
        "title": plan.title,
        "duration_days": plan.duration_days,
        "months": months,
        "price_toman": plan.price_toman,
        "per_month_toman": round(plan.price_toman / months),
        "saving_percent": saving,
        # شناسه‌ی همین پلن در کافه‌بازار (خرید از داخلِ اپِ اندروید)
        "bazaar_sku": bazaar.sku_for(plan.code),
    }


def status_payload(child) -> dict:
    sub = subscription(child)
    renew = renewal_plan(sub)
    current = sub.plan
    return {
        "child_id": str(child.id),
        "child_name": child_name(child),
        "status": "active" if sub.active else "free",
        # همیشگی: بی‌تاریخِ پایان و بی‌صورت‌حسابِ تمدید
        "lifetime": sub.lifetime,
        "plan_code": current.plan.code if current else None,
        "plan_title": "همیشگی" if sub.lifetime else current.plan_title if current else "رایگان",
        "starts_at": sub.chain_start.isoformat() if sub.chain_start else None,
        "ends_at": sub.ends_at.isoformat() if sub.ends_at else None,
        "ends_at_fa": _fa_date(sub.ends_at),
        "days_left": sub.days_left,
        "total_days": sub.total_days,
        "expiring_soon": sub.expiring_soon,
        # اشتراکِ کافه‌بازار که خودِ بازار تمدیدش می‌کند (لغو هم فقط از خودِ بازار)
        "auto_renews": sub.auto_renews,
        "renewal": None if sub.lifetime or sub.auto_renews else {
            "plan_code": renew.code,
            "plan_title": renew.title,
            "amount_toman": renew.price_toman,
            # تمدید پشتِ دوره‌ی فعلی می‌نشیند؛ روزِ باقی‌مانده نمی‌سوزد
            "starts_from_fa": _fa_date(sub.ends_at) if sub.active else _fa_date(timezone.now()),
        } if renew else None,
    }


def payment_payload(payment: Payment) -> dict:
    return {
        "id": payment.id,
        "factor_number": payment.factor_number,
        "child_id": str(payment.child_id) if payment.child_id else None,
        "child_name": payment.child_name,
        "plan_code": payment.plan.code,
        "plan_title": payment.plan_title,
        "amount_toman": payment.amount_toman,
        "status": payment.status,
        "status_label": "هدیه" if payment.source == Payment.Source.GIFT and payment.status == Payment.Status.PAID
        else payment.get_status_display(),
        "is_gift": payment.source == Payment.Source.GIFT,
        "gateway": payment.gateway,
        "created_at_fa": _fa_datetime(payment.created_at),
        "paid_at_fa": _fa_datetime(payment.paid_at),
        "trans_id": payment.trans_id,
        "card_number": payment.card_number,
        "starts_at_fa": _fa_date(payment.starts_at),
        "ends_at_fa": _fa_date(payment.ends_at),
        "message": payment.message if payment.status != Payment.Status.PAID else "",
    }


def _error(message: str, code: int) -> Response:
    """همان پاکتِ خطای بقیه‌ی API (پنل `error.message` را نشان می‌دهد)."""
    return Response({"error": {"code": code, "message": message}}, status=code)


def _visible_payments(user):
    """پرداخت‌هایی که این والد می‌بیند: خودش پرداخته، یا برای بچه‌ی متصل به اوست."""
    children = [c.id for c in linked_children(user)]
    return Payment.objects.filter(Q(payer=user) | Q(child_id__in=children)).select_related("plan")


class PlansView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        monthly = _monthly_price()
        return Response([plan_payload(p, monthly) for p in Plan.objects.filter(is_active=True)])


class ChildrenStatusView(APIView):
    """وضعیتِ اشتراکِ هر فرزند (نشانِ نوار و صفحه‌ی اشتراک)."""

    permission_classes = [IsParent]

    def get(self, request):
        return Response([status_payload(child) for child in linked_children(request.user)])


class PaymentsView(APIView):
    """صورت‌حساب‌ها؛ ?child=<id> فقط همان فرزند."""

    permission_classes = [IsParent]

    def get(self, request):
        rows = _visible_payments(request.user).exclude(status=Payment.Status.PENDING, token__isnull=True)
        child = request.query_params.get("child")
        if child:
            rows = rows.filter(child_id=child)
        return Response([payment_payload(p) for p in rows[:50]])


class PaymentDetailView(APIView):
    """یک پرداخت (صفحه‌ی نتیجه). ?refresh=1 پرداختِ pending را با درگاه پیگیری می‌کند."""

    permission_classes = [IsParent]

    def get(self, request, pk):
        payment = _visible_payments(request.user).filter(pk=pk).first()
        if payment is None:
            return _error("این صورت‌حساب پیدا نشد.", status.HTTP_404_NOT_FOUND)
        if payment.status == Payment.Status.PENDING and request.query_params.get("refresh"):
            payment = reconcile(payment.id) or payment
        return Response(payment_payload(payment))


class CheckoutView(APIView):
    """POST {childId, plan} → {paymentId, payUrl}؛ مرورگر به payUrl (درگاهِ زیبال یا وندار) می‌رود."""

    permission_classes = [IsParent]

    def post(self, request):
        child = is_linked(request.user, request.data.get("child_id"))
        if child is None:
            return _error("این فرزند به حسابِ شما وصل نیست.", status.HTTP_404_NOT_FOUND)
        plan = Plan.objects.filter(code=request.data.get("plan"), is_active=True).first()
        if plan is None:
            return _error("پلنِ انتخاب‌شده پیدا نشد.", status.HTTP_400_BAD_REQUEST)
        try:
            payment = start_checkout(request.user, child, plan, host=request.get_host())
        except CheckoutError as exc:
            return _error(exc.message, exc.status)
        return Response({
            "payment_id": payment.id,
            "factor_number": payment.factor_number,
            "amount_toman": payment.amount_toman,
            "gateway": payment.gateway,
            "pay_url": pay_url(payment),
        }, status=status.HTTP_201_CREATED)


class BazaarVerifyView(APIView):
    """
    POST {childId, plan, purchaseToken, orderId?} — اپِ اندروید بعد از خرید (یا بازیابیِ خرید) با Poolakey
    توکن را می‌فرستد؛ سرور با APIِ کافه‌بازار تأییدش می‌کند → وضعیتِ تازه‌ی اشتراکِ همان فرزند.
    """

    permission_classes = [IsParent]

    def post(self, request):
        child = is_linked(request.user, request.data.get("child_id"))
        if child is None:
            return _error("این فرزند به حسابِ شما وصل نیست.", status.HTTP_404_NOT_FOUND)
        plan = Plan.objects.filter(code=request.data.get("plan")).first()
        if plan is None:
            return _error("پلنِ انتخاب‌شده پیدا نشد.", status.HTTP_400_BAD_REQUEST)
        try:
            payment = verify_bazaar_purchase(request.user, child, plan, str(request.data.get("purchase_token") or ""),
                                             str(request.data.get("order_id") or ""))
        except CheckoutError as exc:
            return _error(exc.message, exc.status)
        return Response({"payment": payment_payload(payment), "subscription": status_payload(child)})


class CallbackView(APIView):
    """بازگشتِ مرورگر از وندار (?token=…&payment_status=OK|FAILED) → صفحه‌ی نتیجه."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def _handle(self, request):
        params = request.query_params if request.method == "GET" else request.data
        token = str(params.get("token") or "").strip()[:128]
        payment = handle_callback(token, str(params.get("payment_status") or "").upper())
        return HttpResponseRedirect(_result_url(payment))

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)


GO_PAGE = """<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="origin"><meta name="robots" content="noindex">
<title>انتقال به درگاهِ پرداخت</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f3ef;color:#1d2128;
font-family:Vazirmatn,Tahoma,sans-serif;text-align:center}}main{{padding:24px}}p{{margin:0 0 14px;font-size:15px}}
a{{display:inline-block;padding:11px 20px;border-radius:14px;background:#215e61;color:#fff;text-decoration:none;
font-weight:700}}</style></head>
<body><main><p>در حالِ انتقال به درگاهِ امنِ زیبال…</p>
<a id="go" href="{url}" referrerpolicy="origin" rel="external">رفتن به درگاه</a></main>
<script>document.getElementById("go").click();</script></body></html>"""


class ZibalGoView(APIView):
    """
    صفحه‌ی گذر روی دامنه‌ی ثبت‌شده‌ی درگاه (panel.luko.ir): زیبال صفحه‌ی پرداخت را فقط با Refererِ همین دامنه
    باز می‌کند. فقط برای پرداختِ زیبالِ در انتظار؛ هر چیزِ دیگر به صفحه‌ی نتیجه برمی‌گردد (بازکنِ آزادِ
    نشانی‌ها نیست).
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, track_id: str):
        from django.http import HttpResponse

        from . import zibal

        payment = Payment.objects.filter(token=track_id, gateway=Payment.Gateway.ZIBAL).first() \
            if track_id.isdigit() else None
        if payment is None or payment.status != Payment.Status.PENDING:
            return HttpResponseRedirect(_result_url(payment))
        response = HttpResponse(GO_PAGE.format(url=zibal.pay_url(payment.token)), content_type="text/html; charset=utf-8")
        response["Cache-Control"] = "no-store"
        return response


class ZibalCallbackView(APIView):
    """بازگشتِ مرورگر از زیبال (GET ?trackId=…&success=1|0&status=…&orderId=…) → صفحه‌ی نتیجه."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def _handle(self, request):
        params = request.query_params if request.method == "GET" else request.data
        track_id = str(params.get("trackId") or "").strip()[:32]
        payment = handle_zibal_callback(track_id if track_id.isdigit() else "", str(params.get("success") or ""))
        return HttpResponseRedirect(_result_url(payment))

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)


def _result_url(payment):
    from .services import result_url

    return result_url(payment, "" if payment else "unknown")

