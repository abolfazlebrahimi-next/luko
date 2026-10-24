"""
پرداختِ درون‌برنامه‌ایِ کافه‌بازار — اشتراکِ اپِ اندروید.

قانونِ بازار (developers.cafebazaar.ir/fa/app-publish-guidelines/rules/payment): اپی که در بازار منتشر می‌شود
اشتراک را **فقط** با پرداختِ بازار می‌فروشد؛ درگاهِ دیگر یا پیوند به سایت برای خرید ممنوع است. سایت همچنان زیبال
دارد. اپ با Poolakey اشتراک می‌خرد و توکنِ خرید را به ما می‌دهد؛ این‌جا با APIِ توسعه‌دهندگانِ بازار (روشِ جدید:
توکنِ پیشخان در هدرِ CAFEBAZAAR-PISHKHAN-API-SECRET) راستی‌آزمایی می‌شود:

    GET {BAZAAR_BASE_URL}/applications/<package>/subscriptions/<sku>/purchases/<token>/
        → {kind, initiationTimestampMsec, validUntilTimestampMsec, autoRenewing, linkedSubscriptionToken}
        404 {error: not_found} یعنی چنین اشتراکی نیست؛ پاسخِ موفق لزوماً فعال نیست — validUntil را بسنج.

توکنِ پیشخان فقط در BAZAAR_API_TOKENِ محیطِ سرور است (مخزن عمومی است).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from urllib.parse import quote

import requests
from django.conf import settings

log = logging.getLogger("luko.billing")

CONNECT_TIMEOUT = 3


class BazaarError(Exception):
    """`transient`: شبکه یا خطای سرورِ بازار — بعداً دوباره؛ وگرنه بازار خرید را رد کرده است."""

    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.message = message
        self.transient = transient


@dataclass
class BazaarSubscription:
    started_at: datetime
    valid_until: datetime
    auto_renewing: bool
    linked_token: str
    raw: dict


def configured() -> bool:
    return bool(settings.BAZAAR_API_TOKEN and settings.BAZAAR_PACKAGE_NAME)


def sku_for(plan_code: str) -> str | None:
    return settings.BAZAAR_SKUS.get(plan_code) or None


def plan_code_for(sku: str) -> str | None:
    return next((code for code, value in settings.BAZAAR_SKUS.items() if value == sku), None)


def _ms(value) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=dt_timezone.utc)


def subscription_status(sku: str, purchase_token: str) -> BazaarSubscription:
    if not configured():
        raise BazaarError("پرداختِ بازار روی سرور تنظیم نشده است.", transient=False)
    url = (f"{settings.BAZAAR_BASE_URL.rstrip('/')}/applications/{quote(settings.BAZAAR_PACKAGE_NAME)}"
           f"/subscriptions/{quote(sku)}/purchases/{quote(purchase_token, safe='')}/")
    try:
        res = requests.get(url, headers={"CAFEBAZAAR-PISHKHAN-API-SECRET": settings.BAZAAR_API_TOKEN},
                           timeout=(CONNECT_TIMEOUT, settings.BAZAAR_TIMEOUT))
    except requests.RequestException as exc:
        raise BazaarError(f"network: {exc.__class__.__name__}", transient=True) from exc
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code == 404 or (isinstance(data, dict) and data.get("error") in ("not_found", "invalid_value")):
        raise BazaarError(f"bazaar: {data.get('error') or 404}", transient=False)
    if res.status_code >= 500 or res.status_code == 429:
        raise BazaarError(f"bazaar http {res.status_code}", transient=True)
    if res.status_code != 200 or not isinstance(data, dict) or "validUntilTimestampMsec" not in data:
        log.error("bazaar validate %s: http %s %s", sku, res.status_code, str(data)[:200])
        raise BazaarError(f"bazaar http {res.status_code}", transient=False)
    try:
        return BazaarSubscription(
            started_at=_ms(data.get("initiationTimestampMsec") or data["validUntilTimestampMsec"]),
            valid_until=_ms(data["validUntilTimestampMsec"]),
            auto_renewing=bool(data.get("autoRenewing")),
            linked_token=str(data.get("linkedSubscriptionToken") or ""),
            raw=data,
        )
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise BazaarError("bazaar: bad timestamps", transient=False) from exc
