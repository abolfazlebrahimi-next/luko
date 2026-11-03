from rest_framework import serializers

from .models import KidSettings, Lukorian, User
from .utils import normalize_phone


class UserSerializer(serializers.ModelSerializer):
    # فرانت id را رشته می‌خواهد (type User.id: string)
    id = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "role", "first_name", "last_name", "phone", "phone_verified",
                  "grade"]


class MeUpdateSerializer(serializers.ModelSerializer):
    """
    مشخصات — گامِ آخرِ ثبت‌نام، بعد از تأییدِ شماره و رمز.

    پایه فقط برای دانش‌آموز معنا دارد و برای بقیه نادیده گرفته می‌شود.
    نقش و شماره عمداً اینجا نیستند تا از این راه عوض نشوند.
    """

    grade = serializers.IntegerField(required=False, min_value=1, max_value=6)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "grade"]

    def validate(self, attrs):
        if self.instance is not None and self.instance.role != User.Role.STUDENT:
            attrs.pop("grade", None)
        return attrs

    def validate_first_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("اسمت را بنویس.")
        return value


class PhoneField(serializers.CharField):
    """شماره را نرمال و اعتبارسنجی می‌کند (۰۹xxxxxxxxx)."""

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        phone = normalize_phone(raw)
        if phone is None:
            raise serializers.ValidationError("شماره‌ی موبایل معتبر نیست.")
        return phone


class StartAuthSerializer(serializers.Serializer):
    """شماره و نقش — پایه‌ی ورود با رمز."""

    phone = PhoneField()
    role = serializers.ChoiceField(
        choices=[("student", "student"), ("parent", "parent")],
        required=False, default="student",
    )


class PasswordLoginSerializer(StartAuthSerializer):
    password = serializers.CharField(min_length=1, max_length=128, trim_whitespace=False)


class SetPasswordSerializer(serializers.Serializer):
    """رمزِ تازه — هم برای گامِ آخرِ ثبت‌نام، هم برای «رمزم را فراموش کردم»."""

    password = serializers.CharField(min_length=6, max_length=128, trim_whitespace=False)

    def validate_password(self, value):
        if value.strip() == "":
            raise serializers.ValidationError("رمز نمی‌تواند خالی باشد.")
        if value.isdigit() and len(set(value)) < 3:
            raise serializers.ValidationError("رمزِ ساده‌ای انتخاب نکن؛ کمی سخت‌ترش کن.")
        return value


class VerifyPhoneSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=4, max_length=12)


class RequestOTPSerializer(serializers.Serializer):
    phone = PhoneField()


class VerifyOTPSerializer(serializers.Serializer):
    phone = PhoneField()
    # طولِ کد را ارائه‌دهنده تعیین می‌کند، نه ما. ملی‌پیامک خودش کد می‌سازد و
    # نمونه‌ی مستنداتش ۱۰ رقمی است؛ سقفِ ۸ رقمِ قبلی همان را رد می‌کرد.
    code = serializers.CharField(min_length=4, max_length=12)
    # فقط هنگام ثبت‌نامِ حسابِ تازه استفاده می‌شوند
    first_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    referral_code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    # نقشِ حسابِ تازه. عمداً محدود است: نقش‌های کارکنان (معلم/مدرسه/ادمین) هرگز
    # از سمتِ کاربر ساخته نمی‌شوند و نقشِ حسابِ موجود هم با این تغییر نمی‌کند.
    role = serializers.ChoiceField(
        choices=[("student", "student"), ("parent", "parent")],
        required=False, default="student",
    )


class KidSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = KidSettings
        fields = ["sound", "music", "mood_reminder", "extra"]


class LukorianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lukorian
        fields = ["unlocked", "is_built", "owned_items", "config", "custom_status"]
        read_only_fields = ["unlocked", "custom_status"]
