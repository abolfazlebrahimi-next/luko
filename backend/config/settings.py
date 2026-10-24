"""
تنظیمات Django برای بک‌اند LUKO.

سکوی داده: PostgreSQL (JSONB برای وضعیت باغچه و رویدادهای تحلیلی).
لایه‌ی سرعت: Redis — هم cache صفحه/خلاصه‌ها و هم broker سلری برای ریست‌های زمان‌بندی‌شده.
قرارداد سیم با فرانت: بدنه‌ی camelCase و پاکت { data | error } (renderers.py).
"""
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    return [x.strip() for x in env(key, default).split(",") if x.strip()]


# ---------------------------------------------------------------------------
# پایه
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# جنگو یکتا بودنِ USERNAME_FIELD را الزامی می‌داند، اما اینجا یکتایی روی
# جفتِ (شماره، نقش) است و ورودِ کاربران با OTP انجام می‌شود نه این مسیر.
# `get_by_natural_key` هم ابهامِ ورودِ ادمین را قطعی حل می‌کند.
SILENCED_SYSTEM_CHECKS = ["auth.E003"]

AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

INSTALLED_APPS = [
    "apps.common.admin_config.LukoAdminConfig",   # به‌جای django.contrib.admin
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    # local apps
    "apps.common",
    "apps.accounts",
    "apps.health",
    "apps.club",
    "apps.garden",
    "apps.games",
    "apps.content",
    "apps.parent",
    "apps.support",
    "apps.sync",
    "apps.billing",
    "apps.activity",
    "apps.notices",
    "apps.blog",
    "apps.dashboard",
    "apps.ai",
    "apps.learn",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # کار در پنلِ جنگو نشستِ مشترک با داشبورد را «بی‌کار» نمی‌گذارد
    "apps.dashboard.middleware.AdminActivityMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# دیتابیس — PostgreSQL (پیش‌فرض) با گزینه‌ی SQLite برای چک سریع
# ---------------------------------------------------------------------------
if env_bool("USE_SQLITE", False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # اپ چند نوشتنِ هم‌زمان دارد (رویدادهای بازی، تکمیلِ مرحله، هم‌رسانیِ
            # دستگاه). SQLite کلِ پایگاه را قفل می‌کند و بی‌این‌ها «database is
            # locked» (خطای ۵۰۰) می‌داد؛ روی Postgresِ سرور چنین قفلی نیست.
            "OPTIONS": {
                "timeout": 20,
                "transaction_mode": "IMMEDIATE",
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "luko"),
            "USER": env("POSTGRES_USER", "luko"),
            "PASSWORD": env("POSTGRES_PASSWORD", "luko"),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }

# ---------------------------------------------------------------------------
# Redis — cache (django-redis). کلیدها و helperها در apps/common/cache.py
# ---------------------------------------------------------------------------
REDIS_CACHE_URL = env("REDIS_CACHE_URL", "redis://localhost:6379/1")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,  # اگر Redis پایین بود، اپ نخوابد (fallback به DB)
            # redis-py اگر hiredis نصب باشد خودش parserِ سریع را برمی‌دارد.
        },
        "KEY_PREFIX": "luko",
        "TIMEOUT": 300,
    }
}
DJANGO_REDIS_IGNORE_EXCEPTIONS = True

# ---------------------------------------------------------------------------
# Celery — broker/backend روی Redis؛ ریست‌های هفتگی/فصلی
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = "Asia/Tehran"
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_EAGER", False)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# کارهای هوش مصنوعی (چند ثانیه تا یک دقیقه) صفِ خودشان را دارند تا کارهای پرداخت پشتشان نمانند
CELERY_TASK_ROUTES = {"apps.ai.tasks.*": {"queue": "ai"}}

# ---------------------------------------------------------------------------
# هوش مصنوعی — AIaaSِ آروان‌کلاد (گیت‌وی سازگار با OpenAI روی api.luko.ir)
# کلید فقط در .env سرور است و هرگز کامیت نمی‌شود. بی‌کلید همه‌چیز با متن‌های قاعده‌محور کار می‌کند.
# ---------------------------------------------------------------------------
AI_BASE_URL = env("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = env("AI_API_KEY", "")
AI_ENABLED = env_bool("AI_ENABLED", bool(AI_BASE_URL and AI_API_KEY))
#: سه مدلِ گیت‌وی؛ پایه رایگان است، دو تای دیگر فقط با اشتراک
AI_MODEL_FLASH = env("AI_MODEL_FLASH", "DeepSeek-V4-Flash")
AI_MODEL_PRO = env("AI_MODEL_PRO", "DeepSeek-V4-Pro")
AI_MODEL_LUNA = env("AI_MODEL_LUNA", "GPT-5.6-Luna")
#: تحلیلِ پس‌زمینه برای فرزندِ مشترک با کدام مدل (flash | pro | luna). Luna در آزمون‌ها ۸ تا ۱۱ ثانیه با
#: حدودِ ۱۰۰۰ توکن؛ Pro از ۲۵ تا ۱۵۰ ثانیه با ۴۵۰۰ توکن (بیشترش استدلال) — کیفیتِ هر دو خوب
AI_INSIGHT_TIER_PREMIUM = env("AI_INSIGHT_TIER_PREMIUM", "luna")
AI_TIMEOUT = int(env("AI_TIMEOUT", "120"))
#: سهمیه‌ی **هفتگیِ** دستیار برای هر والد (هفته از شنبه): بی‌اشتراک فقط «لوکو سریع»
AI_QUOTA_FREE = int(env("AI_QUOTA_FREE", "5"))
AI_QUOTA_PREMIUM = {
    "flash": int(env("AI_QUOTA_PREMIUM_FLASH", "20")),
    "luna": int(env("AI_QUOTA_PREMIUM_LUNA", "10")),
    "pro": int(env("AI_QUOTA_PREMIUM_PRO", "5")),
}
#: سقفِ تحلیل‌های شبانه (بچه‌های فعالِ دیروز)
AI_NIGHTLY_LIMIT = int(env("AI_NIGHTLY_LIMIT", "300"))

# ---------------------------------------------------------------------------
# پیامک (OTP) — sms.ir
# کلیدها فقط از .env خوانده می‌شوند و هرگز کامیت نمی‌شوند.
# SMS_BACKEND=console یعنی چیزی ارسال نمی‌شود و کد فقط در لاگ می‌آید (توسعه).
# ---------------------------------------------------------------------------
# کلیدِ امضای لینکِ فایل‌های بازی. nginx با همین کلید امضا را بررسی می‌کند،
# پس هر دو باید یکی باشند. در production حتماً از env بیاید.
GAME_LINK_SECRET = env("GAME_LINK_SECRET", "dev-game-link-secret")

# پوشه‌ی فایل‌های بازی — `sync_games` کاتالوگ را از نامِ همین فایل‌ها می‌سازد.
# محلی: `frontend/public/games`؛ روی سرور همان `frontend/dist/games` که nginx
# سرو می‌کند، فقط‌خواندنی داخلِ کانتینر (docker-compose.arvan.yml).
GAME_FILES_DIR = Path(env("GAME_FILES_DIR", str(BASE_DIR.parent / "frontend" / "public" / "games")))

# ملی‌پیامک (ارائه‌دهنده‌ی قبلی) — کلید در URLِ سرویس می‌نشیند، پس فقط از env
# کلیدِ گاوصندوقِ رمز — بدونِ آن، رمزِ خوانا اصلاً ذخیره نمی‌شود و پنل
# ادمین «پیکربندی نشده» نشان می‌دهد. فقط در env سرور بماند.
PASSWORD_VAULT_KEY = env("PASSWORD_VAULT_KEY", "")

MELIPAYAMAK_API_KEY = env("MELIPAYAMAK_API_KEY", "")
MELIPAYAMAK_BASE_URL = env("MELIPAYAMAK_BASE_URL", "https://console.melipayamak.com")
MELIPAYAMAK_TIMEOUT = float(env("MELIPAYAMAK_TIMEOUT", "12"))

# ارائه‌دهنده‌ی فعلی sms.ir است. ملی‌پیامک در کد مانده ولی ارسالش رد می‌شد
# («متن حاوی لینک می‌باشد» — الگوی پیامکش در پنلشان لینک داشت).
SMS_BACKEND = env("SMS_BACKEND", "console" if DEBUG else "smsir")

# اجرای تست هرگز نباید پیامکِ واقعی بفرستد (و اعتبار بسوزاند یا کند شود).
if "test" in sys.argv or os.environ.get("PYTEST_CURRENT_TEST"):
    SMS_BACKEND = "console"
    # تست هرگز به گیت‌وی یا صفِ واقعیِ هوش مصنوعی نمی‌رسد (تستِ استقرار با همان .envِ سرور اجرا می‌شود)؛
    # تست‌های apps.ai خودشان با گیت‌وی ساختگی روشنش می‌کنند
    AI_ENABLED = False
    AI_API_KEY = ""
    # کلیدِ ثابتِ آزمایشی برای گاوصندوقِ رمز. بدونِ این، هر توسعه‌دهنده‌ای که
    # PASSWORD_VAULT_KEY در .env ندارد تست‌های گاوصندوق را سبز می‌بیند در حالی
    # که `seal` چیزی ذخیره نکرده — یعنی قابلیت بی‌صدا آزموده نمی‌شود. ثابت
    # بودنش هم یعنی کلیدِ واقعیِ کسی وارد مسیرِ تست نمی‌شود.
    PASSWORD_VAULT_KEY = "kelid-e-azmayeshi-faqat-baraye-test"
    # کش نمی‌تواند LocMem شود: OTP عمداً از اتصالِ خامِ Redis استفاده می‌کند
    # (setex/incr اتمیک). به‌جایش دیتابیسِ جدا تا با داده‌ی توسعه قاطی نشود.
    # پایگاهِ ۱۵ روی همان ردیسی که خودِ برنامه دارد. آدرس از REDIS_CACHE_URL
    # مشتق می‌شود نه ثابتِ localhost، وگرنه تست داخلِ کانتینر — که ردیس آن‌جا
    # `redis` نام دارد — به هیچ‌جا وصل نمی‌شود و ده‌ها تستِ OTP می‌افتند.
    REDIS_CACHE_URL = env("REDIS_TEST_URL", REDIS_CACHE_URL.rsplit("/", 1)[0] + "/15")
    CACHES["default"]["LOCATION"] = REDIS_CACHE_URL
# ---------------------------------------------------------------------------
# درگاهِ پرداختِ وندار (apps/billing). کلید فقط در .env سرور است.
VANDAR_API_KEY = env("VANDAR_API_KEY", "")
VANDAR_BASE_URL = env("VANDAR_BASE_URL", "https://ipg.vandar.io")
VANDAR_TIMEOUT = float(env("VANDAR_TIMEOUT", "15"))
# درگاهِ زیبال. کدِ پذیرنده فقط در .env سرور است («zibal» = حسابِ آزمایشیِ خودِ زیبال).
ZIBAL_MERCHANT = env("ZIBAL_MERCHANT", "")
ZIBAL_BASE_URL = env("ZIBAL_BASE_URL", "https://gateway.zibal.ir")
ZIBAL_TIMEOUT = float(env("ZIBAL_TIMEOUT", "15"))
#: درگاهِ پرداخت‌های تازه: zibal | vandar. پیش‌فرض زیبال وقتی کدِ پذیرنده‌اش هست (وندار IPِ سرور را
#: هرگز مجاز نکرد؛ همه‌ی پرداخت‌های وندار تا ۲۴ مهر ۱۴۰۵ با «آی‌پی مجاز نیست» رد شدند)
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", "zibal" if ZIBAL_MERCHANT else "vandar").strip().lower()
#: نشانیِ عمومیِ سایت: بازگشت از درگاه و صفحه‌ی نتیجه روی همین است
SITE_URL = env("SITE_URL", f"https://{env('LUKO_DOMAIN', 'my.luko.ir')}")
#: دامنه‌ای که درگاهِ زیبال برایش ثبت شده (کدِ پذیرنده‌ی لوکو: panel.luko.ir). callbackUrl باید روی همین باشد
#: و زیبال صفحه‌ی پرداخت را فقط با Refererِ همین دامنه باز می‌کند؛ برای همین پرداخت از این دامنه شروع می‌شود
ZIBAL_SITE_URL = env("ZIBAL_SITE_URL", "") or SITE_URL
# پرداختِ درون‌برنامه‌ایِ کافه‌بازار (apps/billing/bazaar.py) — اپِ اندرویدِ منتشرشده در بازار اشتراک را فقط با
# پرداختِ بازار می‌فروشد. توکنِ APIِ پیشخان فقط در .env سرور است.
BAZAAR_PACKAGE_NAME = env("BAZAAR_PACKAGE_NAME", "")
BAZAAR_API_TOKEN = env("BAZAAR_API_TOKEN", "")
BAZAAR_BASE_URL = env("BAZAAR_BASE_URL", "https://pardakht.cafebazaar.ir/devapi/v2/api")
BAZAAR_TIMEOUT = float(env("BAZAAR_TIMEOUT", "15"))
#: کدِ پلن ← شناسه‌ی محصولِ اشتراک (SKU) در پیشخانِ بازار
BAZAAR_SKUS = {
    "monthly": env("BAZAAR_SKU_MONTHLY", "luko_monthly"),
    "yearly": env("BAZAAR_SKU_YEARLY", "luko_yearly"),
}
#: سایتِ لندینگ که وبلاگ را از API عمومی می‌خواند (فقط همین‌ها CORS می‌گیرند)
BLOG_CORS_ORIGINS = env_list("BLOG_CORS_ORIGINS", "https://luko.ir,https://www.luko.ir")

SMS_IR_API_KEY = env("SMS_IR_API_KEY", "")
SMS_IR_TEMPLATE_ID = env("SMS_IR_TEMPLATE_ID", "")
# نامِ پارامتر داخلِ قالبِ پنل sms.ir (مثلاً {CODE} در متن قالب)
SMS_IR_PARAM_NAME = env("SMS_IR_PARAM_NAME", "CODE")
SMS_IR_BASE_URL = env("SMS_IR_BASE_URL", "https://api.sms.ir")
SMS_IR_TIMEOUT = float(env("SMS_IR_TIMEOUT", "10"))
# در حالتِ توسعه، کد در پاسخِ API هم برگردد تا تست بدون پیامک ممکن باشد.
# محافظِ واقعی در خودِ ویو است: کد فقط وقتی برمی‌گردد که DEBUG هم روشن باشد.
OTP_EXPOSE_DEV_CODE = env_bool("OTP_EXPOSE_DEV_CODE", DEBUG)

# ---------------------------------------------------------------------------
# Django REST Framework + JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # همان JWT، به‌علاوه‌ی بررسیِ نسخه‌ی نشست: ورود از دستگاهِ تازه
        # نشستِ قبلی را می‌بندد. (apps/accounts/sessions.py)
        "apps.accounts.sessions.SessionAwareJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("apps.common.renderers.EnvelopeJSONRenderer",),
    "DEFAULT_PARSER_CLASSES": ("djangorestframework_camel_case.parser.CamelCaseJSONParser",),
    "EXCEPTION_HANDLER": "apps.common.exceptions.envelope_exception_handler",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 30,
    # سقفِ گرفتنِ لینکِ بازی — جلوی برداشتِ انبوهِ فایل‌ها را می‌گیرد
    "DEFAULT_THROTTLE_CLASSES": (),
    # سقفی که برداشتِ انبوه را می‌بندد ولی جلوی بچه‌ی پرکار را نگیرد:
    # هر بازکردنِ بازی یک درخواست است و ۲۷ مرحله بیشتر نداریم.
    "DEFAULT_THROTTLE_RATES": {"play_link": "90/hour", "sync": "1200/hour",
                               # ضربانِ حضور: دقیقه‌ای یکی برای هر صفحه؛ یک مدرسه پشتِ یک IP
                               "presence": "240/min",
                               # رویدادِ بازی: اپ هر ۵ ثانیه یک دسته می‌فرستد (۷۲۰ در ساعت)
                               "game_events": "1500/hour"},
}

# محتوای JSONFieldها (payloadِ رویدادهای بازی، وضعیت باغچه، رنگ‌های نقاشی) نباید
# snake_case شود؛ بازی‌ها کلیدها را camelCase می‌فرستند و تحلیلِ گزارشِ والدین
# روی همان کلیدها انجام می‌شود. (نامِ تنظیم را خودِ کتابخانه تعیین می‌کند.)
JSON_CAMEL_CASE = {
    "JSON_UNDERSCOREIZE": {
        "ignore_fields": ("payload", "state", "colors", "extra", "ingredients"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("ACCESS_TOKEN_MINUTES", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("REFRESH_TOKEN_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# امنیتِ production
#
# همه پشتِ `not DEBUG` هستند تا توسعه‌ی محلی (http) دست‌نخورده بماند.
# فرض: اپ پشتِ nginx با TLS اجرا می‌شود و nginx هدرِ X-Forwarded-Proto می‌فرستد.
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "31536000"))   # یک سال
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "SAMEORIGIN"        # بازی‌ها داخلِ iframe هم‌ریشه اجرا می‌شوند

    # نشستِ پنلِ ادمین. پیش‌فرضِ جنگو دو هفته است؛ برای پنلی که دادهٔ بچه‌ها و
    # رمزِ خوانای پشتیبانی را نشان می‌دهد، کوکیِ دو هفته‌ای روی لپ‌تاپِ گم‌شده
    # زیادی سخاوتمند است. فقط ادمین را تحت تأثیر می‌گذارد: خودِ اپ با JWT کار
    # می‌کند و نشستِ جنگو ندارد.
    SESSION_COOKIE_AGE = int(env("DJANGO_SESSION_HOURS", "8")) * 3600
    SESSION_SAVE_EVERY_REQUEST = True          # کار کردن، نشست را زنده نگه می‌دارد
    # نشست و CSRF فقط در درخواست‌های هم‌سایت (پنلِ جنگو و داشبورد). اپ با JWT کار می‌کند و
    # بازگشت از درگاهِ پرداخت هم به نشستِ جنگو نیاز ندارد، پس Strict چیزی را نمی‌شکند.
    SESSION_COOKIE_SAMESITE = "Strict"
    CSRF_COOKIE_SAMESITE = "Strict"

    if SECRET_KEY == "dev-insecure-key-change-me":
        raise RuntimeError(
            "DJANGO_SECRET_KEY تنظیم نشده است. با DEBUG=0 نباید کلیدِ توسعه استفاده شود."
        )

# نشانیِ پنلِ ادمین. «admin/» شناخته‌شده است و هر اسکنری اول همان را می‌زند؛
# مسیرِ غیرِحدس‌زدنی جلوی سر و صدای خودکار را می‌گیرد. لایه‌ی اصلیِ امنیت
# نیست (رمز و سقفِ تلاش هستند) ولی هزینه‌ای هم ندارد. از env عوض می‌شود تا
# بی‌نیاز به دیپلوی قابلِ تغییر باشد.
ADMIN_URL = env("DJANGO_ADMIN_URL", "v1a2n3r4").strip("/")

# داشبوردِ مدیریت (apps.dashboard): نشانیِ بلند و غیرِحدس‌زدنی فقط در .envِ سرور است؛
# اپِ داشبورد آن را از نشانیِ صفحه می‌خواند و در هیچ فایلِ عمومی‌ای نیست. API زیرِ
# «/<مسیر>/api/» است. لایه‌ی اصلیِ امنیت ورودِ دومرحله‌ای و دسترسی‌هاست، نه پنهان‌بودنِ نشانی.
DASHBOARD_PATH = env("DASHBOARD_PATH", "").strip("/") or "dash-local"
#: روی سرور داشبورد فقط با نشانیِ بلند سوار می‌شود؛ مقدارِ خالی یا کوتاه یعنی اصلاً نباشد
#: (بهتر از این‌که روی «/dash-local/» حدس‌زدنی بالا بیاید). در توسعه همیشه هست.
DASHBOARD_ENABLED = DEBUG or len(DASHBOARD_PATH) >= 24
#: بی‌کاری بیش از این، نشستِ داشبورد را می‌بندد
DASHBOARD_IDLE_MINUTES = int(env("DASHBOARD_IDLE_MINUTES", "30"))
#: عمرِ کلِ نشستِ داشبورد، هر قدر هم فعال باشد
DASHBOARD_SESSION_HOURS = int(env("DASHBOARD_SESSION_HOURS", "8"))

# دامنه‌هایی که مجازند فرمِ POST بفرستند (پشتِ https)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# i18n / static
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# فایل‌هایی که از پنلِ ادمین بارگذاری می‌شوند (فعلاً صوتِ پادکست‌ها). روی سرور
# همان volumeِ «media» است که nginx زیرِ /media/ سرو می‌کند (docker-compose.arvan.yml).
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
