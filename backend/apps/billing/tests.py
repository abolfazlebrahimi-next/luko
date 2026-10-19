"""
اشتراک و پرداخت در برابرِ یک وندارِ ساختگی که رفتارِ مستند را دارد:
verify فقط یک‌بار جواب می‌دهد، transaction کدِ ۰..۴ می‌دهد، و پاسخ می‌تواند گم شود.
هیچ درخواستی به اینترنت نمی‌رود.
"""
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.parent.models import Notification, ParentChild
from apps.parent.notifications import sync_notifications

from . import services, tasks
from .models import Payment, Plan

KEY = "test-vandar-key"


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


class FakeVandar:
    """وندارِ ساختگی. `unpaid_code` کدی است که transaction برای تراکنشِ پرداخت‌نشده می‌دهد."""

    def __init__(self, unpaid_code=1):
        self.tx = {}
        self.calls = []
        self.down = False
        self.lose_next_verify = False
        self.amount_override = None
        self.unpaid_code = unpaid_code
        self.next_token = 1000

    # --- کارهای «خریدار» در صفحه‌ی بانک
    def pay(self, token):
        self.tx[token]["paid"] = True

    def fail(self, token):
        self.tx[token]["failed"] = True

    # --- همان requests.post
    def post(self, url, json=None, timeout=None, headers=None):
        path = url.split("/api/v4/")[-1]
        self.calls.append((path, json))
        if self.down:
            raise requests.ConnectionError("down")
        if json.get("api_key") != KEY:
            return FakeResponse(422, {"status": 0, "errors": ["کلید نامعتبر است"]})
        if path == "send":
            if json["amount"] < 1000:
                return FakeResponse(422, {"status": 0, "errors": ["مبلغ کمتر از حد مجاز"]})
            self.next_token += 1
            token = f"tok{self.next_token}"
            self.tx[token] = {"amount": json["amount"], "paid": False, "verified": False,
                              "failed": False, "expired": False, "factor": json.get("factorNumber")}
            return FakeResponse(200, {"status": 1, "token": token})
        t = self.tx.get(json.get("token"))
        if t is None:
            return FakeResponse(422, {"status": 0, "errors": ["توکن نامعتبر"]})
        amount = self.amount_override or t["amount"]
        if path == "verify":
            if not t["paid"] or t["verified"] or t["expired"]:
                return FakeResponse(422, {"status": 0, "errors": ["تراکنش قابل تایید نیست"]})
            t["verified"] = True
            if self.lose_next_verify:
                self.lose_next_verify = False
                raise requests.ReadTimeout("lost")
            return FakeResponse(200, {"status": 1, "amount": f"{amount}.00", "realAmount": amount,
                                      "wage": "0", "transId": 159178352177, "factorNumber": t["factor"],
                                      "cardNumber": "603799******7999", "message": "ok",
                                      "paymentDate": "2026-10-04 10:00:00"})
        if path == "transaction":
            if t["verified"]:
                code = 2
            elif t["expired"]:
                code = 3
            elif t["failed"]:
                code = 4
            elif t["paid"]:
                code = 1
            else:
                code = self.unpaid_code
            body = {"status": 1 if code in (1, 2) else 0, "amount": f"{amount}.00", "transId": 159178352177,
                    "cardNumber": "603799******7999", "code": code, "message": "x"}
            return FakeResponse(200 if code in (1, 2) else 422, body)
        return FakeResponse(404, {})


@override_settings(VANDAR_API_KEY=KEY, VANDAR_BASE_URL="https://ipg.vandar.io",
                   SITE_URL="https://my.luko.ir", PAYMENT_GATEWAY="vandar")
class BillingTestBase(TestCase):
    unpaid_code = 1

    def setUp(self):
        cache.clear()      # گاردِ یک‌دقیقه‌ایِ همگام‌سازیِ اعلان‌ها بینِ تست‌ها نماند
        self.vandar = FakeVandar(self.unpaid_code)
        patcher = mock.patch("apps.billing.vandar.requests.post", side_effect=self.vandar.post)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.parent = User.objects.create(phone="09120000001", role=User.Role.PARENT, first_name="مادر")
        self.other_parent = User.objects.create(phone="09120000009", role=User.Role.PARENT)
        self.guardian = User.objects.create(phone="09120000002", role=User.Role.PARENT, first_name="پدر")
        self.child = User.objects.create(phone="09120000003", role=User.Role.STUDENT, first_name="سارا")
        self.stranger_child = User.objects.create(phone="09120000004", role=User.Role.STUDENT)
        ParentChild.objects.create(parent=self.parent, child=self.child)
        ParentChild.objects.create(parent=self.guardian, child=self.child)
        ParentChild.objects.create(parent=self.other_parent, child=self.stranger_child)
        self.monthly = Plan.objects.get(code="monthly")
        self.yearly = Plan.objects.get(code="yearly")
        self.api = APIClient()
        self.api.force_authenticate(self.parent)

    def checkout(self, plan="monthly", child=None):
        res = self.api.post("/api/v1/billing/checkout",
                            {"childId": str((child or self.child).id), "plan": plan}, format="json")
        return res

    def callback(self, token, status="OK"):
        anon = APIClient()
        return anon.get("/api/v1/billing/callback", {"token": token, "payment_status": status})

    def buy(self, plan="monthly"):
        res = self.checkout(plan)
        self.assertEqual(res.status_code, 201, res.content)
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.vandar.pay(payment.token)
        self.callback(payment.token)
        payment.refresh_from_db()
        return payment


class PlansAndStatusTests(BillingTestBase):
    def test_plans_are_seeded_with_prices_and_saving(self):
        res = self.api.get("/api/v1/billing/plans")
        plans = {p["code"]: p for p in res.json()["data"]}
        self.assertEqual(plans["monthly"]["priceToman"], 199_000)
        self.assertEqual(plans["yearly"]["priceToman"], 1_499_000)
        self.assertEqual(plans["yearly"]["perMonthToman"], 124_917)
        self.assertEqual(plans["yearly"]["months"], 12)
        self.assertEqual(plans["yearly"]["savingPercent"], 37)   # ۱٬۴۹۹٬۰۰۰ در برابرِ ۱۲ × ۱۹۹٬۰۰۰
        self.assertEqual(plans["monthly"]["savingPercent"], 0)

    def test_every_child_is_free_by_default(self):
        res = self.api.get("/api/v1/billing/children")
        rows = res.json()["data"]
        self.assertEqual([r["childId"] for r in rows], [str(self.child.id)])   # نه بچه‌ی والدِ دیگر
        self.assertEqual(rows[0]["status"], "free")
        self.assertEqual(rows[0]["planTitle"], "رایگان")
        self.assertEqual(rows[0]["daysLeft"], 0)
        self.assertIsNone(rows[0]["renewal"])

    def test_students_cannot_use_billing(self):
        student = APIClient()
        student.force_authenticate(self.child)
        self.assertEqual(student.get("/api/v1/billing/children").status_code, 403)
        self.assertEqual(student.post("/api/v1/billing/checkout", {"childId": str(self.child.id),
                                                                   "plan": "monthly"}, format="json").status_code, 403)


class CheckoutTests(BillingTestBase):
    def test_checkout_sends_rial_amount_callback_and_mobile(self):
        res = self.checkout("monthly")
        self.assertEqual(res.status_code, 201)
        data = res.json()["data"]
        self.assertTrue(data["payUrl"].startswith("https://ipg.vandar.io/v4/tok"))
        sent = [c for c in self.vandar.calls if c[0] == "send"][0][1]
        self.assertEqual(sent["amount"], 1_990_000)          # ریال
        self.assertEqual(sent["callback_url"], "https://my.luko.ir/api/v1/billing/callback")
        self.assertEqual(sent["mobile_number"], "09120000001")
        payment = Payment.objects.get(pk=data["paymentId"])
        self.assertEqual(sent["factorNumber"], payment.factor_number)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount_toman, 199_000)

    def test_cannot_buy_for_someone_elses_child_or_unknown_plan(self):
        self.assertEqual(self.checkout(child=self.stranger_child).status_code, 404)
        self.assertEqual(self.checkout(plan="lifetime").status_code, 400)
        self.yearly.is_active = False
        self.yearly.save()
        self.assertEqual(self.checkout(plan="yearly").status_code, 400)

    def test_gateway_down_fails_cleanly(self):
        self.vandar.down = True
        res = self.checkout()
        self.assertEqual(res.status_code, 503)
        self.assertIn("درگاه", res.json()["error"]["message"])
        self.assertEqual(Payment.objects.get().status, Payment.Status.FAILED)

    @override_settings(VANDAR_API_KEY="")
    def test_missing_key_is_a_clear_error(self):
        res = self.checkout()
        self.assertEqual(res.status_code, 502)
        self.assertEqual(Payment.objects.get().status, Payment.Status.FAILED)

    def test_too_many_pending_checkouts_are_throttled(self):
        for _ in range(services.MAX_PENDING_PER_HOUR):
            self.assertEqual(self.checkout().status_code, 201)
        self.assertEqual(self.checkout().status_code, 429)


class CallbackTests(BillingTestBase):
    def test_successful_payment_activates_subscription(self):
        payment = self.buy("monthly")
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.trans_id, "159178352177")
        self.assertEqual(payment.card_number, "603799******7999")
        self.assertAlmostEqual((payment.ends_at - payment.starts_at).days, 30)
        row = self.api.get("/api/v1/billing/children").json()["data"][0]
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["planCode"], "monthly")
        self.assertEqual(row["daysLeft"], 30)
        self.assertEqual(row["renewal"]["planCode"], "monthly")      # تمدید = همان آخرین پلن
        self.assertEqual(row["renewal"]["amountToman"], 199_000)

    def test_callback_redirects_to_result_page(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.vandar.pay(payment.token)
        redirect = self.callback(payment.token)
        self.assertEqual(redirect.status_code, 302)
        url = urlparse(redirect["Location"])
        self.assertEqual(url.netloc, "my.luko.ir")
        self.assertEqual(url.path, "/parent-panel/subscription/result")
        self.assertEqual(parse_qs(url.query)["payment"], [str(payment.id)])

    def test_both_parents_get_the_success_notification(self):
        payment = self.buy()
        for parent in (self.parent, self.guardian):
            note = Notification.objects.get(user=parent, dedup_key=f"payment:{payment.id}")
            self.assertEqual(note.kind, Notification.Kind.BILLING)
            self.assertIn("فعال شد", note.title)
            self.assertIn(f"child={self.child.id}", note.link)
        self.assertFalse(Notification.objects.filter(user=self.other_parent).exists())

    def test_repeated_callback_activates_once(self):
        payment = self.buy()
        verifies = len([c for c in self.vandar.calls if c[0] == "verify"])
        self.callback(payment.token)      # دکمه‌ی «برگشت» مرورگر / رفرش
        self.callback(payment.token)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(len([c for c in self.vandar.calls if c[0] == "verify"]), verifies)
        self.assertEqual(Payment.objects.filter(status=Payment.Status.PAID).count(), 1)

    def test_cancelled_payment_fails_immediately(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.callback(payment.token, "FAILED")       # کاربر در بانک لغو کرد
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(self.api.get("/api/v1/billing/children").json()["data"][0]["status"], "free")

    def test_ok_callback_without_payment_does_not_activate(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.callback(payment.token, "OK")            # پارامترِ دست‌کاری‌شده؛ پولی نیامده
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(self.api.get("/api/v1/billing/children").json()["data"][0]["status"], "free")

    def test_lost_verify_response_is_recovered(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.vandar.pay(payment.token)
        self.vandar.lose_next_verify = True           # وندار تأیید کرد ولی پاسخ به ما نرسید
        self.callback(payment.token)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)      # نه «ناموفق»
        # بازگشتِ دوباره: verify حالا خطا می‌دهد (فقط یک‌بار جواب می‌دهد) و transaction کدِ ۲
        self.callback(payment.token)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_lost_verify_response_is_recovered_by_reconcile(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.vandar.pay(payment.token)
        self.vandar.lose_next_verify = True
        self.callback(payment.token)
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=3))
        tasks.reconcile_pending()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_amount_mismatch_never_activates(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.vandar.pay(payment.token)
        self.vandar.amount_override = 10_000           # وندار مبلغِ دیگری تأیید کرد
        self.callback(payment.token)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(self.api.get("/api/v1/billing/children").json()["data"][0]["status"], "free")

    def test_unknown_token_redirects_with_error(self):
        redirect = self.callback("not-a-token")
        self.assertEqual(redirect.status_code, 302)
        self.assertIn("error=unknown", redirect["Location"])
        self.assertEqual(self.callback("").status_code, 302)

    def test_network_error_during_verify_keeps_payment_pending(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.vandar.pay(payment.token)
        self.vandar.down = True
        self.callback(payment.token)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.vandar.down = False
        detail = self.api.get(f"/api/v1/billing/payments/{payment.id}", {"refresh": 1})
        self.assertEqual(detail.json()["data"]["status"], "pending")   # هنوز زود است (۲ دقیقه)
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=3))
        detail = self.api.get(f"/api/v1/billing/payments/{payment.id}", {"refresh": 1})
        self.assertEqual(detail.json()["data"]["status"], "paid")


class UnpaidCodeZeroCallbackTests(CallbackTests):
    """همان سناریوها اگر وندار برای پرداخت‌نشده کدِ ۴ (نه ۱) بدهد."""

    unpaid_code = 4


class ReconcileTests(BillingTestBase):
    def test_browser_closed_after_paying_is_completed_by_reconcile(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.vandar.pay(payment.token)                 # پرداخت کرد و مرورگر را بست
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=4))
        tasks.reconcile_pending()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_unpaid_stays_pending_inside_the_gateway_window_then_expires(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=5))
        tasks.reconcile_pending()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)       # هنوز روی صفحه‌ی بانک است
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        tasks.reconcile_pending()
        payment.refresh_from_db()
        self.assertIn(payment.status, (Payment.Status.EXPIRED, Payment.Status.FAILED))

    def test_very_old_pending_expires(self):
        res = self.checkout()
        payment = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(days=3))
        tasks.reconcile_pending()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.EXPIRED)


class StackingAndHistoryTests(BillingTestBase):
    def test_renewing_early_keeps_remaining_days(self):
        first = self.buy("monthly")
        # ۲۰ روز گذشته: ۱۰ روز مانده
        Payment.objects.filter(pk=first.pk).update(starts_at=first.starts_at - timedelta(days=20),
                                                   ends_at=first.ends_at - timedelta(days=20))
        second = self.buy("yearly")
        first.refresh_from_db()
        self.assertEqual(second.starts_at, first.ends_at)
        sub = services.subscription(self.child)
        self.assertEqual(sub.days_left, 10 + 365)
        self.assertEqual(sub.plan.pk, first.pk)                         # دوره‌ی جاری هنوز ماهانه است
        row = self.api.get("/api/v1/billing/children").json()["data"][0]
        self.assertEqual(row["renewal"]["planCode"], "yearly")          # آخرین خرید
        self.assertGreaterEqual(row["totalDays"], row["daysLeft"])

    def test_expired_subscription_returns_to_free_but_keeps_renewal_offer(self):
        first = self.buy("yearly")
        Payment.objects.filter(pk=first.pk).update(starts_at=first.starts_at - timedelta(days=400),
                                                   ends_at=first.ends_at - timedelta(days=400))
        row = self.api.get("/api/v1/billing/children").json()["data"][0]
        self.assertEqual(row["status"], "free")
        self.assertEqual(row["renewal"]["planCode"], "yearly")

    def test_history_lists_paid_and_failed_for_linked_parents_only(self):
        self.buy("monthly")
        res = self.checkout("yearly")
        failed = Payment.objects.get(pk=res.json()["data"]["paymentId"])
        self.callback(failed.token, "FAILED")
        rows = self.api.get("/api/v1/billing/payments").json()["data"]
        self.assertEqual([r["status"] for r in rows], ["failed", "paid"])
        self.assertEqual(rows[1]["amountToman"], 199_000)
        self.assertTrue(rows[1]["endsAtFa"])
        # والدِ دومِ همان بچه هم می‌بیند؛ والدِ غریبه نه
        guardian = APIClient()
        guardian.force_authenticate(self.guardian)
        self.assertEqual(len(guardian.get("/api/v1/billing/payments").json()["data"]), 2)
        other = APIClient()
        other.force_authenticate(self.other_parent)
        self.assertEqual(other.get("/api/v1/billing/payments").json()["data"], [])
        self.assertEqual(other.get(f"/api/v1/billing/payments/{failed.id}").status_code, 404)

    def test_days_left_rounds_up_on_the_last_day(self):
        payment = self.buy("monthly")
        now = timezone.now()
        Payment.objects.filter(pk=payment.pk).update(starts_at=now - timedelta(days=29, hours=12),
                                                     ends_at=now + timedelta(hours=12))
        self.assertEqual(services.subscription(self.child).days_left, 1)


class NoticeTests(BillingTestBase):
    def _end_in(self, payment, days):
        now = timezone.now()
        Payment.objects.filter(pk=payment.pk).update(
            starts_at=now - timedelta(days=payment.duration_days - days),
            ends_at=now + timedelta(days=days))

    def test_week_before_the_end_parents_get_a_renewal_link(self):
        payment = self.buy("yearly")
        self._end_in(payment, 6)
        sync_notifications(self.parent, force=True)
        note = Notification.objects.get(user=self.parent, dedup_key__startswith="sub-ending:")
        self.assertIn("رو به پایان", note.title)
        self.assertIn("۶ روزِ دیگر", note.body)
        self.assertEqual(note.link, f"/parent-panel/subscription?child={self.child.id}&plan=yearly")
        sync_notifications(self.parent, force=True)       # تکرار نمی‌سازد
        self.assertEqual(Notification.objects.filter(user=self.parent, dedup_key__startswith="sub-ending:").count(), 1)

    def test_no_notice_more_than_a_week_before(self):
        payment = self.buy("monthly")
        self._end_in(payment, 9)
        sync_notifications(self.parent, force=True)
        self.assertFalse(Notification.objects.filter(dedup_key__startswith="sub-").exists())

    def test_notice_even_when_activity_alerts_are_off(self):
        from apps.parent.notifications import preferences

        pref = preferences(self.parent)
        pref.activity_alerts = False
        pref.weekly_report = False
        pref.save()
        payment = self.buy("monthly")
        self._end_in(payment, 3)
        sync_notifications(self.parent, force=True)
        self.assertTrue(Notification.objects.filter(user=self.parent, dedup_key__startswith="sub-ending:").exists())

    def test_ended_notice_then_nothing_after_a_week(self):
        payment = self.buy("monthly")
        self._end_in(payment, -2)
        sync_notifications(self.parent, force=True)
        note = Notification.objects.get(user=self.parent, dedup_key__startswith="sub-ended:")
        self.assertIn("تمام شد", note.title)
        self.assertIn("plan=monthly", note.link)
        Notification.objects.all().delete()
        self._end_in(payment, -10)
        sync_notifications(self.parent, force=True)
        self.assertFalse(Notification.objects.filter(dedup_key__startswith="sub-").exists())

    def test_daily_task_notifies_every_linked_parent(self):
        payment = self.buy("monthly")
        self._end_in(payment, 5)
        tasks.notify_expiring()
        for parent in (self.parent, self.guardian):
            self.assertTrue(Notification.objects.filter(user=parent, dedup_key__startswith="sub-ending:").exists())

    def test_notification_api_returns_the_link(self):
        payment = self.buy("monthly")
        self._end_in(payment, 4)
        items = self.api.get("/api/v1/parent/notifications").json()["data"]["items"]
        billing = [i for i in items if i["kind"] == "billing" and "رو به پایان" in i["title"]]
        self.assertEqual(len(billing), 1)
        self.assertIn("/parent-panel/subscription?child=", billing[0]["link"])


# ---------------------------------------------------------------------------
# هم‌زمانی — فقط روی Postgres (قفلِ ردیف)؛ در کانتینرِ سرور هنگامِ دیپلوی اجرا می‌شود.
import threading  # noqa: E402
import time  # noqa: E402
from unittest import skipUnless  # noqa: E402

from django.db import connection, connections  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402


@skipUnless(connection.vendor == "postgresql", "قفلِ ردیف فقط روی Postgres آزموده می‌شود")
@override_settings(VANDAR_API_KEY=KEY, VANDAR_BASE_URL="https://ipg.vandar.io", SITE_URL="https://my.luko.ir",
                   PAYMENT_GATEWAY="vandar")
class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.vandar = FakeVandar()
        slow_post = self.vandar.post

        def post(url, **kwargs):
            if url.endswith("/verify"):
                time.sleep(0.3)          # پنجره‌ی رقابت را باز نگه دار
            return slow_post(url, **kwargs)

        patcher = mock.patch("apps.billing.vandar.requests.post", side_effect=post)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plan = Plan.objects.update_or_create(code="monthly", defaults={
            "title": "ماهانه", "duration_days": 30, "price_toman": 199_000})[0]
        self.parent = User.objects.create(phone="09120000101", role=User.Role.PARENT)
        self.child = User.objects.create(phone="09120000103", role=User.Role.STUDENT)
        ParentChild.objects.create(parent=self.parent, child=self.child)

    def _parallel(self, fn, args_list):
        errors = []

        def run(*args):
            try:
                fn(*args)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=run, args=a) for a in args_list]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_simultaneous_returns_from_the_gateway_activate_once(self):
        payment = services.start_checkout(self.parent, self.child, self.plan)
        self.vandar.pay(payment.token)
        self._parallel(services.handle_callback, [(payment.token, "OK")] * 6)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(len([c for c in self.vandar.calls if c[0] == "verify"]), 1)
        self.assertEqual(Payment.objects.filter(status=Payment.Status.PAID).count(), 1)

    def test_two_purchases_at_once_for_one_child_do_not_overlap(self):
        first = services.start_checkout(self.parent, self.child, self.plan)
        second = services.start_checkout(self.parent, self.child, self.plan)
        self.vandar.pay(first.token)
        self.vandar.pay(second.token)
        self._parallel(services.handle_callback, [(first.token, "OK"), (second.token, "OK")])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual({first.status, second.status}, {Payment.Status.PAID})
        a, b = sorted([first, second], key=lambda p: p.starts_at)
        self.assertEqual(b.starts_at, a.ends_at)           # پشتِ هم، نه روی هم
        self.assertEqual(services.subscription(self.child).days_left, 60)


class GiftTests(TestCase):
    """اشتراکِ هدیه از داشبورد."""

    def setUp(self):
        from apps.parent.models import ParentChild

        self.parent = User.objects.create(phone="09120000301", role=User.Role.PARENT)
        self.child = User.objects.create(phone="09120000302", role=User.Role.STUDENT, first_name="نیلا")
        ParentChild.objects.create(parent=self.parent, child=self.child)
        self.staff = User.objects.create_superuser("09120000399", "Gift-Pass-1")

    def test_gift_activates_and_notifies_parent(self):
        from apps.billing.services import gift_subscription, subscription
        from apps.billing.views import payment_payload
        from apps.parent.models import Notification

        payment = gift_subscription(child=self.child, days=14, granted_by=self.staff, note="جبرانِ قطعی")
        sub = subscription(self.child)
        self.assertTrue(sub.active)
        self.assertEqual(sub.days_left, 14)
        self.assertEqual((payment.amount_toman, payment.source, payment.granted_by_id), (0, "gift", self.staff.id))
        note = Notification.objects.get(user=self.parent)
        self.assertIn("هدیه", note.title)
        row = payment_payload(payment)
        self.assertEqual((row["status_label"], row["is_gift"]), ("هدیه", True))

    def test_gift_stacks_after_current_period(self):
        from apps.billing.services import gift_subscription, subscription

        gift_subscription(child=self.child, days=30, granted_by=self.staff)
        gift_subscription(child=self.child, days=10, granted_by=self.staff)
        self.assertEqual(subscription(self.child).days_left, 40)

    def test_rules(self):
        from apps.billing.services import CheckoutError, gift_subscription

        with self.assertRaises(CheckoutError):
            gift_subscription(child=self.parent, days=10, granted_by=self.staff)
        for bad in (0, 731):
            with self.assertRaises(CheckoutError):
                gift_subscription(child=self.child, days=bad, granted_by=self.staff)

    def test_revoke_only_gifts(self):
        from apps.billing.services import CheckoutError, gift_subscription, revoke_gift, subscription

        payment = gift_subscription(child=self.child, days=10, granted_by=self.staff)
        revoke_gift(payment)
        self.assertFalse(subscription(self.child).active)
        real = Payment.objects.create(payer=self.parent, child=self.child, plan=Plan.objects.first(),
                                      plan_title="ماهانه", duration_days=30, amount_toman=199000,
                                      amount_rial=1990000, factor_number="LKREAL1", status="paid")
        with self.assertRaises(CheckoutError):
            revoke_gift(real)


class LifetimeAccessTests(BillingTestBase):
    """ادمین‌ها و گروهِ «اشتراکِ همیشگی» همیشه اشتراکِ کامل دارند — بی‌خرید، بی‌تاریخِ پایان، بی‌یادآوری."""

    def lifetime_group(self):
        from django.contrib.auth.models import Group

        return Group.objects.get_or_create(name=services.LIFETIME_GROUP)[0]

    def test_normal_child_is_unaffected(self):
        self.assertFalse(services.subscription(self.child).lifetime)
        self.assertFalse(services.subscription(self.child).active)

    def test_group_member_parent_gets_lifetime_without_admin_access(self):
        self.parent.groups.add(self.lifetime_group())
        sub = services.subscription(self.child)
        self.assertTrue(sub.active and sub.lifetime)
        self.assertFalse(sub.expiring_soon)
        row = self.api.get("/api/v1/billing/children").json()["data"][0]
        self.assertEqual((row["status"], row["lifetime"], row["planTitle"], row["renewal"]), ("active", True, "همیشگی", None))
        self.parent.refresh_from_db()
        self.assertFalse(self.parent.is_staff or self.parent.is_superuser)   # پنلِ ادمین نه
        # پولی برای اشتراکِ همیشگی گرفته نمی‌شود
        self.assertEqual(self.checkout().status_code, 400)
        self.assertFalse(Payment.objects.filter(child=self.child).exists())
        # یادآوریِ «رو به پایان/تمام شد» هم ندارد
        sync_notifications(self.parent)
        self.assertFalse(Notification.objects.filter(user=self.parent, kind=Notification.Kind.BILLING).exists())

    def test_admin_parent_and_admins_own_phone(self):
        # حسابِ والدِ کسی که شماره‌اش شماره‌ی یک ادمین است (ادمین با نقشِ جدا)
        User.objects.create(phone=self.guardian.phone, role=User.Role.TEAM_ADMIN, is_staff=True)
        self.assertTrue(services.subscription(self.child).lifetime)
        # بچه‌ی والدِ دیگر هنوز رایگان
        self.assertFalse(services.subscription(self.stranger_child).active)

    def test_child_linked_to_admin_or_inactive_link(self):
        admin = User.objects.create(phone="09120000077", role=User.Role.TEAM_ADMIN, is_staff=True, is_superuser=True)
        link = ParentChild.objects.create(parent=admin, child=self.stranger_child)
        self.assertTrue(services.subscription(self.stranger_child).lifetime)
        # پیوندِ قطع‌شده اشتراکِ همیشگی نمی‌دهد
        link.is_active = False
        link.save(update_fields=["is_active"])
        self.assertFalse(services.subscription(self.stranger_child).active)

    def test_premium_features_follow_lifetime(self):
        from apps.ai.assistant import is_premium

        self.assertFalse(is_premium(self.child))
        self.parent.groups.add(self.lifetime_group())
        self.assertTrue(is_premium(self.child))
