import logging

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common import cache
from apps.common.sms import SmsError, _mask

from .constants import BUILDER_PRICES, CUSTOM_CHARACTER
from .models import User
from .otp import (
    OTPIPBlocked,
    OTPRateLimited,
    OTPTooManyAttempts,
    check_ip_quota,
    consume_pick_ticket,
    issue_pick_ticket,
    request_otp,
    verify_otp,
)
from .passwords import (get_or_create_account, has_password, link_family,
                        mark_phone_verified, set_password, student_by_password)
from .sessions import SESSION_CLAIM, end_session, keep_session, new_session
from .serializers import (
    KidSettingsSerializer,
    LukorianSerializer,
    MeUpdateSerializer,
    PasswordLoginSerializer,
    RequestOTPSerializer,
    SetPasswordSerializer,
    UserSerializer,
    VerifyOTPSerializer,
    VerifyPhoneSerializer,
)
from .services import build_profile_stats, get_profile_stats

log = logging.getLogger("luko.auth")


def _client_ip(request) -> str:
    """پشتِ nginx، IP واقعی در اولین مقدارِ X-Forwarded-For است."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _tokens_for(user, fresh=True):
    """
    `fresh=True` یعنی این یک ورودِ تازه است و نشستِ دستگاه‌های قبلی را
    می‌بندد. تمدیدِ توکن با `fresh=False` می‌آید تا خودش کاربر را بیرون
    نیندازد.
    """
    refresh = new_session(user) if fresh else keep_session(user)
    return {"accessToken": str(refresh.access_token), "refreshToken": str(refresh)}


def _auth_payload(user, is_new=False, fresh=True):
    """
    توکن‌ها و کاربر، به‌علاوه‌ی اینکه ثبت‌نامش کجا مانده.

    ثبت‌نام با کدِ پیامکی شروع می‌شود و بعد از تأییدِ شماره دو گام دارد:
    رمز، بعد مشخصات. حسابی که یکی را ندارد — تازه ساخته شده یا از قبل
    نیمه‌کاره مانده — با همین دو پرچم به گامِ درست فرستاده می‌شود؛ فرانت
    خودش حدس نمی‌زند.
    """
    return {
        **_tokens_for(user, fresh),
        "user": UserSerializer(user).data,
        "isNew": is_new,
        "needsPassword": not has_password(user),
        "needsProfile": not (user.first_name or "").strip(),
    }


class RequestOTPView(APIView):
    """گامِ ۱ ورود/ثبت‌نام: ارسالِ رمزِ یکبارمصرف به شماره."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        try:
            check_ip_quota(_client_ip(request))
        except OTPIPBlocked as exc:
            return Response(
                {"error": {"code": 429, "message": "درخواستِ زیادی از این دستگاه ثبت شده؛ بعداً تلاش کن.",
                           "retryAfter": exc.args[0] if exc.args else 3600}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            info = request_otp(phone)
        except OTPRateLimited as exc:
            resend_in = exc.args[0] if exc.args else 60
            return Response(
                {"error": {"code": 429, "message": "کد به‌تازگی ارسال شده؛ کمی صبر کن.",
                           "resendIn": resend_in}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except SmsError as exc:
            # جزئیاتِ فنی فقط در لاگ می‌ماند؛ کاربر پیامِ ساده می‌بیند
            log.error("ارسال OTP ناموفق برای %s — %s", _mask(phone), exc.detail)
            return Response(
                {"error": {"code": 502, "message": exc.message}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # طولِ کد را سرور می‌گوید چون ارائه‌دهنده‌ها یکی نیستند؛ فرانت به
        # همین تعداد خانه می‌سازد و با عوض‌شدنِ پنلِ پیامک نمی‌شکند.
        payload = {
            "expiresIn": info["ttl"],
            "resendIn": info["resend_in"],
            "codeLength": info.get("length") or len(info["code"]),
        }
        if settings.OTP_EXPOSE_DEV_CODE and settings.DEBUG:
            payload["devCode"] = info["code"]  # فقط در حالتِ توسعه، برای تست
        return Response(payload)


class VerifyOTPView(APIView):
    """
    گامِ ۲: بررسیِ کد — هم ورود است هم شروعِ ثبت‌نام.

    حساب نبود، همین‌جا ساخته می‌شود؛ رمز و مشخصات گام‌های بعدند و پرچم‌های
    پاسخ می‌گویند کدام مانده. کدِ درست یعنی شماره واقعاً دستِ خودش است، پس
    شماره تأییدشده ثبت می‌شود.
    """

    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        phone = data["phone"]

        try:
            ok = verify_otp(phone, data["code"])
        except OTPTooManyAttempts:
            return Response(
                {"error": {"code": 400, "message": "چند بار اشتباه زدی؛ کدِ تازه بگیر."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ok:
            return Response(
                {"error": {"code": 400, "message": "کد اشتباه یا منقضی شده."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # نقش بخشی از جستجوست، نه فقط پیش‌فرضِ ساخت. یعنی ورود از صفحه‌ی
        # والدین همیشه به حسابِ والدِ همان شماره می‌رسد و ورود از صفحه‌ی
        # بچه‌ها به حسابِ دانش‌آموزِ همان شماره — دو حسابِ جدا با یک شماره،
        # چون بیشترِ بچه‌ها با شماره‌ی پدر/مادرشان ثبت‌نام می‌کنند. هیچ‌کدام
        # نقشِ دیگری را عوض نمی‌کند و نقشِ کارکنان هم از اینجا ساخته نمی‌شود.
        requested_role = data.get("role") or User.Role.STUDENT

        # یک شماره می‌تواند چند بچه داشته باشد، پس کدِ درست به‌تنهایی
        # نمی‌گوید «کدام بچه». اگر بیش از یکی بود، فهرست را می‌دهیم تا
        # خودش انتخاب کند؛ بلیتِ کوتاه‌عمر ثابت می‌کند کد تأیید شده بوده.
        if requested_role == User.Role.STUDENT:
            siblings = list(User.objects.filter(phone=phone, role=User.Role.STUDENT))
            if len(siblings) > 1:
                return Response({
                    "chooseFrom": [
                        {"id": str(u.id), "firstName": u.first_name, "grade": u.grade}
                        for u in siblings
                    ],
                    "ticket": issue_pick_ticket(phone),
                })
            user = siblings[0] if siblings else None
            is_new = user is None
            if is_new:
                user, _ = get_or_create_account(
                    phone, requested_role, data.get("first_name", "") or "")
        else:
            user, is_new = User.objects.get_or_create(
                phone=phone,
                role=requested_role,
                defaults={
                    "first_name": data.get("first_name", "") or "",
                    "last_name": data.get("last_name", "") or "",
                },
            )
            if is_new:
                user.set_unusable_password()  # ورود فقط با OTP
                user.save(update_fields=["password"])
                link_family(user)
                from apps.parent.referrals import attribute_new_parent
                attribute_new_parent(user, data.get("referral_code", ""))

        if not user.phone_verified:
            mark_phone_verified(user)
        return Response(_auth_payload(user, is_new),
                        status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK)


class OTPChooseView(APIView):
    """
    POST /auth/otp-choose — بعد از تأییدِ کد، انتخابِ اینکه کدام بچه است.

    فقط وقتی لازم می‌شود که چند بچه یک شماره داشته باشند. بلیت ثابت
    می‌کند کدِ همان شماره تازه تأیید شده، وگرنه هر کسی می‌توانست با
    دانستنِ یک شناسه وارد حسابِ دیگری شود.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        ticket = request.data.get("ticket") or ""
        phone = consume_pick_ticket(ticket)
        if phone is None:
            return Response(
                {"error": {"code": 400, "message": "این مرحله منقضی شده؛ دوباره کد بگیر."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(
            pk=request.data.get("user_id") or request.data.get("userId"),
            phone=phone, role=User.Role.STUDENT,
        ).first()
        if user is None:
            return Response(
                {"error": {"code": 404, "message": "این حساب پیدا نشد."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        # بلیت ثابت می‌کند کدِ همین شماره تازه تأیید شده
        if not user.phone_verified:
            mark_phone_verified(user)
        return Response(_auth_payload(user, False))


class RetiredAuthView(APIView):
    """
    `/auth/start` و `/auth/register` — بازنشسته.

    ثبت‌نام حالا اول شماره را با کدِ پیامکی تأیید می‌کند. `register` حساب را
    بدونِ هیچ تأییدی می‌ساخت — هر کسی روی هر شماره‌ای — و `start` بی‌دلیل
    می‌گفت کدام شماره حساب دارد. ۴۱۰ با پیامِ روشن برای نسخه‌ی قدیمیِ اپ که
    هنوز در کشِ گوشی مانده.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        return Response(
            {"error": {
                "code": 410,
                "message": "ورود و ثبت‌نام حالا با کدِ پیامکی است؛ صفحه را یک‌بار تازه کن.",
            }},
            status=status.HTTP_410_GONE,
        )


class PasswordLoginView(APIView):
    """POST /auth/login — ورود با رمز؛ راهِ جایگزین وقتی کدِ پیامکی نمی‌رسد."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        role = serializer.validated_data["role"]

        raw = serializer.validated_data["password"]

        # دانش‌آموز: چند بچه می‌توانند یک شماره داشته باشند و رمز آن‌ها را
        # از هم جدا می‌کند، پس حساب از روی رمز پیدا می‌شود نه فقط شماره.
        if role == User.Role.STUDENT:
            user = student_by_password(phone, raw)
        else:
            found = User.objects.filter(phone=phone, role=role).first()
            user = found if found and has_password(found) and found.check_password(raw) else None

        # پیامِ یکسان برای «شماره نیست» و «رمز غلط» تا شماره‌ها لو نروند
        if user is None:
            return Response(
                {"error": {"code": 400, "message": "شماره یا رمز درست نیست."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.is_active:
            return Response({"error": {"code": 403, "message": "این حساب غیرفعال است."}},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(_auth_payload(user, False))


class SetPasswordView(APIView):
    """
    POST /auth/set-password — گذاشتن یا عوض‌کردنِ رمز.

    گامِ دومِ ثبت‌نام است (بعد از تأییدِ شماره با کد، پیش از مشخصات) و
    مقصدِ «رمزم را فراموش کردم» در پنلِ والدین.
    """

    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_password(request.user, serializer.validated_data["password"])
        return Response(UserSerializer(request.user).data)


class VerifyPhoneView(APIView):
    """
    POST /auth/verify-phone — تأییدِ شماره برای حسابی که فقط با رمز وارد شده.

    ورود با کد خودش شماره را تأیید می‌کند؛ این برای بقیه است.
    """

    def post(self, request):
        serializer = VerifyPhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ok = verify_otp(request.user.phone, serializer.validated_data["code"])
        except OTPTooManyAttempts:
            return Response(
                {"error": {"code": 400, "message": "چند بار اشتباه زدی؛ کدِ تازه بگیر."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ok:
            return Response({"error": {"code": 400, "message": "کد اشتباه یا منقضی شده."}},
                            status=status.HTTP_400_BAD_REQUEST)
        mark_phone_verified(request.user)
        return Response(UserSerializer(request.user).data)


class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # پارسر کلیدهای ورودی را snake_case می‌کند، پس `refreshToken` هرگز
        # خوانده نمی‌شد. بدترش این بود که `RefreshToken(None)` خطا نمی‌دهد و
        # یک توکنِ خالیِ تازه می‌سازد — یعنی این مسیر هیچ چیزی را تأیید
        # نمی‌کرد. توکنِ نبود باید صریح رد شود.
        token = (request.data.get("refresh_token") or request.data.get("refreshToken")
                 or request.data.get("refresh"))
        if not token:
            return Response(
                {"error": {"code": 401, "message": "توکن تمدید نامعتبر است."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            refresh = RefreshToken(token)
        except TokenError:
            return Response(
                {"error": {"code": 401, "message": "توکن تمدید نامعتبر است."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # نشست ممکن است جای دیگری تازه شده باشد. بدونِ این بررسی، توکنِ
        # دستگاهِ قدیمی تا دو هفته می‌توانست توکنِ دسترسیِ تازه بگیرد.
        version = refresh.get(SESSION_CLAIM)
        if version is not None:
            user = User.objects.filter(pk=refresh.get("user_id")).first()
            if user is None or int(version) != user.session_version:
                return Response(
                    {"error": {"code": 401,
                               "message": "از دستگاهِ دیگری وارد شده‌ای؛ دوباره وارد شو."}},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        return Response({"accessToken": str(refresh.access_token)})


class LogoutView(APIView):
    """
    خروج — نشست همین‌جا بسته می‌شود، نه فقط روی گوشی.

    قرارِ محصول این است که بچه دو هفته وارد بماند مگر جای دیگری وارد شود
    یا خودش خارج شود. پس خروج باید شمارنده‌ی نشست را جلو ببرد، وگرنه توکنِ
    refreshِ باقی‌مانده تا آخرِ همان دو هفته حساب را باز می‌کرد.

    ملاک، توکنِ **refresh** است نه access: عمرِ access نیم ساعت است و کسی
    که بعد از مدتی برنامه را باز می‌کند و همان اول «خروج» می‌زند، توکنِ
    منقضی دارد — آن‌وقت خروج در احراز هویت رد می‌شد و نشست تا دو هفته
    زنده می‌ماند. refresh دقیقاً همان چیزی است که آن دو هفته را می‌دهد،
    پس بستنِ نشست با نشان‌دادنش درست است.

    احراز هویتِ هدر عمداً برداشته شده: اگر هدرِ `Authorization` منقضی باشد،
    DRF پیش از رسیدن به این متد ۴۰۱ می‌دهد و خروج اصلاً اجرا نمی‌شود. پس
    شناسه فقط از خودِ refresh خوانده می‌شود. پاسخ همیشه موفق است: کسی که
    خارج شده نباید پیامِ خطا ببیند، و این‌طور معلوم هم نمی‌شود کدام توکن
    معتبر بوده است.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token = (request.data.get("refresh_token") or request.data.get("refreshToken")
                 or request.data.get("refresh"))
        user = None

        if token:
            try:
                refresh = RefreshToken(token)
            except TokenError:
                refresh = None
            if refresh is not None:
                candidate = User.objects.filter(pk=refresh.get("user_id")).first()
                version = refresh.get(SESSION_CLAIM)
                # توکنِ عقب‌مانده نباید نشستِ تازه را ببندد، وگرنه هر کسی با
                # یک توکنِ سوخته می‌توانست دستگاهِ فعلی را بیرون بیندازد.
                if candidate is not None and (
                    version is None or int(version) == candidate.session_version
                ):
                    user = candidate

        if user is not None:
            end_session(user)
        return Response({"success": True})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        """
        مشخصات — گامِ آخرِ ثبت‌نام، بعد از تأییدِ شماره و رمز.

        پایه این‌جا انتخاب می‌شود نه هنگامِ ساختِ حساب (حساب با کد و پیش از
        هر سؤالی ساخته می‌شود). والدِ هم‌شماره همان لحظه وصل شده و پیوندش
        پایه‌ی پیش‌فرض را دارد، پس همراهش به‌روز می‌شود.
        """
        user = request.user
        before = user.grade
        serializer = MeUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if user.role == User.Role.STUDENT and user.grade != before:
            from apps.parent.models import ParentChild
            ParentChild.objects.filter(child=user).update(grade=user.grade)
        return Response(UserSerializer(user).data)


class ProfileStatsView(APIView):
    """آمار واقعیِ صفحه‌ی پروفایل — سکه/امتیاز/بازی/مدال/استریک/گنج/لوکوریان."""

    def get(self, request):
        return Response(get_profile_stats(request.user))


class SettingsView(APIView):
    def get(self, request):
        return Response(KidSettingsSerializer(request.user.settings).data)

    def patch(self, request):
        serializer = KidSettingsSerializer(
            request.user.settings, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class TreasureView(APIView):
    """موجودی گنج (فقط خواندن؛ کسبِ گنج سمت سرور از دستاوردها انجام می‌شود)."""

    def get(self, request):
        return Response({"treasures": request.user.profile.treasures})


class LukorianView(APIView):
    def get(self, request):
        return Response(LukorianSerializer(request.user.lukorian).data)

    def patch(self, request):
        """ذخیره‌ی پیکربندی/ساختِ کاراکتر (فقط اگر کارگاه باز شده باشد)."""
        luk = request.user.lukorian
        if not luk.unlocked:
            return Response(
                {"error": {"code": 403, "message": "هنوز کارگاه برایت باز نشده."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = LukorianSerializer(luk, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class LukorianUnlockView(APIView):
    """باز کردن کارگاه — فقط اگر همه‌ی آستانه‌ها (سکه/مأموریت/استریک/بازی) برقرار باشد."""

    def post(self, request):
        stats = build_profile_stats(request.user)
        if not stats["builderUnlock"]["canUnlock"]:
            return Response(
                {"error": {"code": 403, "message": "هنوز شرط‌های باز شدن کارگاه کامل نیست.",
                           "details": stats["builderUnlock"]}},
                status=status.HTTP_403_FORBIDDEN,
            )
        luk = request.user.lukorian
        luk.unlocked = True
        luk.save(update_fields=["unlocked", "updated_at"])
        cache.invalidate(cache.profile_key(request.user.id))
        return Response(LukorianSerializer(luk).data)


class LukorianBuyView(APIView):
    """خرید آیتم ظاهری با گنج — قیمت‌ها سمت سرور، اعتبارسنجی موجودی."""

    def post(self, request):
        item = request.data.get("item")
        price = BUILDER_PRICES.get(item)
        if price is None:
            return Response(
                {"error": {"code": 400, "message": "آیتم نامعتبر."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = request.user.profile
        luk = request.user.lukorian
        if item in luk.owned_items:
            return Response(LukorianSerializer(luk).data)  # قبلاً خریده
        if profile.treasures < price:
            return Response(
                {"error": {"code": 400, "message": "گنج کافی نداری."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile.treasures -= price
        profile.save(update_fields=["treasures", "updated_at"])
        luk.owned_items = [*luk.owned_items, item]
        luk.save(update_fields=["owned_items", "updated_at"])
        cache.invalidate(cache.profile_key(request.user.id))
        return Response(LukorianSerializer(luk).data)


class LukorianCustomRequestView(APIView):
    """درخواستِ ساخت کاراکتر از عکس بچه — گران، سمت سرور کسر می‌شود."""

    def post(self, request):
        profile = request.user.profile
        luk = request.user.lukorian
        price = CUSTOM_CHARACTER["priceTreasure"]
        if luk.custom_status != luk.CustomStatus.NONE:
            return Response(LukorianSerializer(luk).data)
        if profile.treasures < price:
            return Response(
                {"error": {"code": 400, "message": "گنج کافی نداری."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile.treasures -= price
        profile.save(update_fields=["treasures", "updated_at"])
        luk.custom_status = luk.CustomStatus.REQUESTED
        luk.save(update_fields=["custom_status", "updated_at"])
        cache.invalidate(cache.profile_key(request.user.id))
        return Response(
            {**LukorianSerializer(luk).data, "deliveryDays": CUSTOM_CHARACTER["deliveryDays"]}
        )
