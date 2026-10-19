"""شکلِ داده‌های کاربر برای فهرست و صفحه‌ی جزئیات."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.accounts.models import Profile, User
from apps.activity.services import ONLINE_WINDOW, user_activity
from apps.billing.models import Payment
from apps.billing.services import subscription
from apps.common.constants import GRADE_CHOICES
from apps.common.fa import fa_date, fa_digits, fa_time
from apps.content.models import PodcastListen
from apps.games.models import Game, GameCompletion
from apps.parent.models import ParentChild
from apps.support.models import Ticket

from . import capabilities
from .audit import ACTIONS
from .models import AuditLog
from .segments import ROLE_LABELS, SUB_LABELS, sub_end_subquery, sub_status_of

GRADES = dict(GRADE_CHOICES)
PLATFORM_LABELS = {"web": "وب", "android": "اندروید"}


def fa_ago(moment: datetime | None, now: datetime) -> str:
    if moment is None:
        return ""
    delta = now - moment
    if delta < timedelta(minutes=1):
        return "همین الان"
    if delta < timedelta(hours=1):
        return f"{fa_digits(int(delta.total_seconds() // 60))} دقیقه پیش"
    local = timezone.localtime(moment)
    if delta < timedelta(hours=24) and local.date() == timezone.localdate(now):
        return f"{fa_digits(int(delta.total_seconds() // 3600))} ساعت پیش"
    days = (timezone.localdate(now) - local.date()).days
    if days == 1:
        return f"دیروز، {fa_time(local)}"
    if days < 7:
        return f"{fa_digits(days)} روز پیش"
    return fa_date(local.date(), with_year=days > 300)


def fa_stamp(moment: datetime | None) -> str:
    if moment is None:
        return ""
    local = timezone.localtime(moment)
    return f"{fa_date(local.date(), with_year=True)} · {fa_time(local)}"


def full_name(user: User | None) -> str:
    if user is None:
        return ""
    return f"{user.first_name} {user.last_name}".strip()


def role_of(user: User) -> dict:
    if user.is_superuser:
        key = "admin"
    elif user.is_staff:
        key = "staff"
    else:
        key = user.role
    label = ROLE_LABELS.get(key, key)
    if key == "staff":
        title = getattr(getattr(user, "staff_access", None), "title", "")
        label = title or label
    return {"key": key, "label": label}


def last_seen(user: User, now: datetime) -> dict:
    """آخرین بازدید؛ برای حساب‌های پیش از ثبتِ حضور، آخرین ورود (تقریبی)."""
    at, estimated = user.last_seen_at, False
    if at is None and user.last_login:
        at, estimated = user.last_login, True
    return {
        "at": at.isoformat() if at else None,
        "fa": fa_ago(at, now) if at else "هنوز نیامده",
        "platform": user.last_seen_platform if user.last_seen_at else "",
        "platform_label": PLATFORM_LABELS.get(user.last_seen_platform, "") if user.last_seen_at else "",
        "online": bool(user.last_seen_at and now - user.last_seen_at <= ONLINE_WINDOW),
        "estimated": estimated,
    }


def sub_payload(end: datetime | None, now: datetime) -> dict:
    status = sub_status_of(end, now)
    running = bool(end and end > now)
    return {
        "status": status, "label": SUB_LABELS[status],
        "ends_fa": fa_date(timezone.localtime(end).date(), with_year=True) if end else "",
        # همان قاعده‌ی billing.subscription: روزِ ناقص یک روز حساب می‌شود
        "days_left": max(1, math.ceil((end - now) / timedelta(days=1))) if running else 0,
        "expired": bool(end and end <= now),
    }


def rows(users: list[User], now: datetime) -> list[dict]:
    """ردیف‌های یک صفحه‌ی فهرست؛ اشتراکِ فرزندانِ والدها با یک کوئری."""
    parent_ids = [u.pk for u in users if u.role == User.Role.PARENT and not u.is_staff]
    children: dict[int, list] = {}
    if parent_ids:
        links = ParentChild.objects.filter(parent_id__in=parent_ids, is_active=True) \
            .annotate(child_end=_child_end()).values_list("parent_id", "child_end")
        for parent_id, end in links:
            children.setdefault(parent_id, []).append(sub_status_of(end, now))
    out = []
    for user in users:
        role = role_of(user)
        row = {
            "id": user.pk,
            "name": full_name(user) or "بی‌نام",
            "phone": user.phone,
            "role": role["key"],
            "role_label": role["label"],
            "grade": user.grade if user.role == User.Role.STUDENT else None,
            "grade_label": GRADES.get(user.grade, "") if user.role == User.Role.STUDENT else "",
            "is_active": user.is_active,
            "phone_verified": user.phone_verified,
            "joined_fa": fa_date(timezone.localtime(user.date_joined).date(), with_year=True),
            "last_seen": last_seen(user, now),
            "subscription": None,
            "children": None,
        }
        if role["key"] == "student":
            row["subscription"] = sub_payload(getattr(user, "sub_end", None), now)
        elif role["key"] == "parent":
            statuses = children.get(user.pk, [])
            row["children"] = {
                "count": len(statuses),
                "active": statuses.count("active"),
                "renewal": statuses.count("renewal"),
                "inactive": statuses.count("inactive"),
            }
        out.append(row)
    return out


def _child_end():
    from django.db.models import OuterRef, Subquery

    return Subquery(Payment.objects.filter(child=OuterRef("child_id"), status=Payment.Status.PAID,
                                           ends_at__isnull=False).order_by("-ends_at").values("ends_at")[:1])


def payment_row(p: Payment) -> dict:
    return {
        "id": p.id,
        "factor": p.factor_number,
        "child_id": p.child_id,
        "child_name": p.child_name or full_name(p.child),
        "payer_id": p.payer_id,
        "payer_phone": p.payer_phone or (p.payer.phone if p.payer_id and p.payer else ""),
        "plan_title": p.plan_title,
        "days": p.duration_days,
        "amount_toman": p.amount_toman,
        "status": p.status,
        "status_label": "هدیه" if p.source == Payment.Source.GIFT and p.status == Payment.Status.PAID
        else p.get_status_display(),
        "source": p.source,
        "granted_by": full_name(p.granted_by) or (p.granted_by.phone if p.granted_by_id else ""),
        "note": p.note,
        "created_fa": fa_stamp(p.created_at),
        "paid_fa": fa_stamp(p.paid_at),
        "ends_fa": fa_date(timezone.localtime(p.ends_at).date(), with_year=True) if p.ends_at else "",
        "trans_id": p.trans_id,
        "message": p.message,
    }


def detail(user: User, now: datetime, viewer: User) -> dict:
    """همه‌چیز درباره‌ی یک کاربر — صفحه‌ی جزئیات."""
    role = role_of(user)
    user.sub_end = User.objects.filter(pk=user.pk).annotate(e=sub_end_subquery()).values_list("e", flat=True).first()
    base = rows([user], now)[0]
    data = {
        **base,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "joined_stamp": fa_stamp(user.date_joined),
        "last_login_fa": fa_stamp(user.last_login),
        "last_seen_stamp": fa_stamp(user.last_seen_at),
        "activity": None, "parents": [], "children_list": [], "payments": [], "tickets": [],
        "progress": None, "staff": None, "history": [],
    }
    activity = user_activity(user, 30, now)
    activity["series"] = [{"day": fa_date(r["day"]), "minutes": r["minutes"]} for r in activity["series"]]
    data["activity"] = activity

    if role["key"] == "student":
        sub = subscription(user, now)
        data["subscription"].update({"plan": "همیشگی" if sub.lifetime else sub.plan.plan_title if sub.plan else "",
                                     "total_days": sub.total_days})
        data["parents"] = [
            {"id": link.parent_id, "name": full_name(link.parent) or "بی‌نام", "phone": link.parent.phone}
            for link in ParentChild.objects.filter(child=user, is_active=True).select_related("parent")
        ]
        done = GameCompletion.objects.filter(user=user)
        last = done.order_by("-created_at").first()
        profile = Profile.objects.filter(user=user).first()
        data["progress"] = {
            "games_done": done.count(),
            "stars": sum(done.values_list("stars", flat=True)),
            "last_game": (Game.objects.filter(slug=last.game_slug).values_list("title", flat=True).first()
                          or last.game_slug) if last else "",
            "last_game_fa": fa_ago(last.created_at, now) if last else "",
            "coins": profile.coins if profile else 0,
            "points": profile.points if profile else 0,
            "podcast_listens": PodcastListen.objects.filter(user=user).count(),
        }
        payments = Payment.objects.filter(child=user)
    elif role["key"] == "parent":
        links = list(ParentChild.objects.filter(parent=user, is_active=True).select_related("child")
                     .annotate(child_end=_child_end()))
        data["children_list"] = [
            {"id": link.child_id, "name": full_name(link.child) or "بی‌نام",
             "grade_label": GRADES.get(link.child.grade, ""),
             "subscription": sub_payload(link.child_end, now),
             "last_seen": last_seen(link.child, now)}
            for link in links
        ]
        payments = Payment.objects.filter(Q(payer=user) | Q(child_id__in=[link.child_id for link in links]))
        data["tickets"] = [
            {"id": t.id, "subject": t.subject, "status": t.status, "status_label": t.get_status_display(),
             "updated_fa": fa_ago(t.last_at or t.updated_at, now)}
            for t in Ticket.objects.filter(user=user).annotate(last_at=Max("messages__created_at"))
            .order_by("-updated_at")[:10]
        ]
    else:
        payments = Payment.objects.none()
        if user.is_staff:
            access = getattr(user, "staff_access", None)
            data["staff"] = {"title": access.title if access else "", "capabilities": capabilities.of(user)}

    if "payments" in capabilities.of(viewer):
        data["payments"] = [payment_row(p) for p in payments.select_related("child", "payer", "granted_by")
                            .order_by("-created_at")[:20]]
    if "audit" in capabilities.of(viewer):
        data["history"] = [
            {"action": ACTIONS.get(a.action, a.action), "by": a.actor_label, "at": fa_stamp(a.created_at),
             "details": a.details}
            for a in AuditLog.objects.filter(target_type="user", target_id=str(user.pk))[:10]
        ]
    return data


def counts_by_role() -> dict:
    agg = User.objects.aggregate(
        students=Count("pk", filter=Q(role=User.Role.STUDENT, is_staff=False)),
        parents=Count("pk", filter=Q(role=User.Role.PARENT, is_staff=False)),
        staff=Count("pk", filter=Q(is_staff=True)),
    )
    return agg
