"""اپلیکیشن Celery + زمان‌بندی ریست‌های هفتگی و فصلی."""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("luko")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# زمان‌بندی: هر شنبه ۰۰:۰۵ ریستِ نمای هفته‌ی کلاب؛ روزانه ۰۰:۱۰ چک تغییر فصلِ باغچه.
app.conf.beat_schedule = {
    "club-weekly-reset-saturday": {
        "task": "apps.club.tasks.rollover_week",
        "schedule": crontab(hour=0, minute=5, day_of_week="saturday"),
    },
    "garden-seasonal-check-daily": {
        "task": "apps.garden.tasks.apply_seasonal_resets",
        "schedule": crontab(hour=0, minute=10),
    },
    # پرداختی که مرورگرش از درگاه برنگشت؛ زیبال و وندار تا ۲۰ دقیقه تأیید می‌پذیرند
    "billing-reconcile-pending": {
        "task": "apps.billing.tasks.reconcile_pending",
        "schedule": crontab(minute="*/3"),
    },
    # تمدیدِ خودکارِ اشتراک‌های کافه‌بازار نزدیکِ پایانِ هر دوره
    "billing-refresh-bazaar": {
        "task": "apps.billing.tasks.refresh_bazaar_subscriptions",
        "schedule": crontab(minute=17, hour="*/3"),
    },
    # یادآوریِ تمدید از ۷ روز پیش از پایانِ اشتراک
    "billing-notify-expiring-daily": {
        "task": "apps.billing.tasks.notify_expiring",
        "schedule": crontab(hour=9, minute=30),
    },
    # تحلیلِ هوشمندِ بچه‌های فعالِ دیروز، پیش از آن‌که والدها صبح پنل را باز کنند
    "ai-refresh-recent-nightly": {
        "task": "apps.ai.tasks.refresh_recent",
        "schedule": crontab(hour=4, minute=40),
    },
    "activity-prune-daily": {
        "task": "apps.activity.tasks.prune_activity",
        "schedule": crontab(hour=4, minute=20),
    },
}
