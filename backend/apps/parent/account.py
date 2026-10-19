"""
تنظیماتِ پنلِ والدین: مشخصاتِ کاملِ هر فرزند و رمزِ خودِ والد.

GET   /parent/children/{id}/profile   مشخصات، حضور، آمارِ کلی و اشتراکِ فرزند
PATCH /parent/children/{id}           نام، نام خانوادگی و مدرسه (پایه از این راه عوض نمی‌شود)
POST  /parent/password                تغییرِ رمزِ والد — با رمزِ فعلی، اگر رمزی دارد
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.passwords import has_password, set_password
from apps.accounts.services import get_profile_stats
from apps.billing.services import subscription
from apps.common.constants import GRADE_CHOICES
from apps.common.fa import fa_date, fa_digits, fa_when
from apps.games.models import GameCompletion
from apps.health.models import MoodCheckin, Painting

from .models import ParentChild
from .permissions import IsParent

GRADE_FA = dict(GRADE_CHOICES)
ONLINE_MINUTES = 3


def _error(message: str, code: int = 400) -> Response:
    return Response({"error": {"code": code, "message": message}}, status=code)


def _link(request, child_id) -> ParentChild | None:
    return ParentChild.objects.filter(parent=request.user, child_id=child_id, is_active=True) \
        .select_related("child").first()


def child_profile(link: ParentChild) -> dict:
    child = link.child
    now = timezone.now()
    today = timezone.localdate()
    stats = get_profile_stats(child)
    sub = subscription(child)
    last_play = GameCompletion.objects.filter(user=child).order_by("-created_at") \
        .values_list("created_at", flat=True).first()
    seen = max((t for t in (child.last_seen_at, last_play) if t), default=None)
    joined = timezone.localtime(child.date_joined)
    return {
        "id": str(child.id),
        "first_name": child.first_name,
        "last_name": child.last_name,
        "phone": child.phone,
        "phone_verified": child.phone_verified,
        "grade": link.grade,
        "grade_label": f"پایه‌ی {GRADE_FA.get(link.grade, fa_digits(link.grade))}",
        "school": link.school,
        "relation": link.get_relation_display(),
        "joined_fa": fa_date(joined.date(), with_year=True),
        "joined_days": (today - joined.date()).days,
        "linked_fa": fa_date(timezone.localtime(link.created_at).date(), with_year=True),
        "last_seen_fa": fa_when(timezone.localtime(seen), today) if seen else "",
        "platform": child.last_seen_platform or "",
        "online": bool(child.last_seen_at and (now - child.last_seen_at).total_seconds() < ONLINE_MINUTES * 60),
        "stats": {
            "coins": stats["coins"],
            "points": stats["points"],
            "treasures": stats["treasures"],
            "games_completed": stats["gamesCompleted"],
            "medals": stats["medalsUnlocked"],
            "tasks": stats["totalTasks"],
            "streak": stats["streak"],
            "paintings": Painting.objects.filter(user=child).count(),
            "checkins": MoodCheckin.objects.filter(user=child).count(),
        },
        "subscription": {
            "active": sub.active,
            "lifetime": sub.lifetime,
            "plan_title": "همیشگی" if sub.lifetime else sub.plan.plan_title if sub.active and sub.plan else "رایگان",
            "days_left": sub.days_left if sub.active else 0,
            "ends_fa": fa_date(timezone.localtime(sub.ends_at).date(), with_year=True) if sub.active and sub.ends_at else "",
        },
    }


class ChildUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    school = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_first_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("نامِ فرزند خالی نمی‌ماند.")
        return value


class ChildProfileView(APIView):
    permission_classes = [IsParent]

    def get(self, request, child_id):
        link = _link(request, child_id)
        if link is None:
            return _error("فرزند پیدا نشد.", 404)
        return Response(child_profile(link))


def update_child(request, child_id) -> Response:
    """PATCH روی /parent/children/{id} — از ChildDetailView صدا زده می‌شود"""
    link = _link(request, child_id)
    if link is None:
        return _error("فرزند پیدا نشد.", 404)
    serializer = ChildUpdateSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    child = link.child
    fields = [f for f in ("first_name", "last_name") if f in data]
    for field in fields:
        setattr(child, field, data[field].strip())
    if fields:
        child.save(update_fields=fields)
    if "school" in data:
        link.school = data["school"].strip()
        link.save(update_fields=["school", "updated_at"])
    from .services import invalidate_child_report

    invalidate_child_report(child.id)
    return Response(child_profile(link))


class ParentPasswordSerializer(serializers.Serializer):
    current = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False, default="")
    password = serializers.CharField(min_length=6, max_length=128, trim_whitespace=False)

    def validate_password(self, value):
        if value.strip() == "":
            raise serializers.ValidationError("رمز نمی‌تواند خالی باشد.")
        if value.isdigit() and len(set(value)) < 3:
            raise serializers.ValidationError("رمزِ ساده‌ای است؛ کمی سخت‌ترش کنید.")
        return value


class ParentPasswordView(APIView):
    """رمزِ والد: اگر رمزی دارد، رمزِ فعلی لازم است (گوشیِ بازمانده نباید رمز را عوض کند)."""

    permission_classes = [IsParent]

    def post(self, request):
        serializer = ParentPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        data = serializer.validated_data
        if has_password(user) and not user.check_password(data["current"]):
            return _error("رمزِ فعلی درست نیست.")
        if has_password(user) and data["current"] == data["password"]:
            return _error("رمزِ تازه با رمزِ فعلی یکی است.")
        set_password(user, data["password"])
        return Response({"ok": True, "has_password": True})

    def get(self, request):
        return Response({"has_password": has_password(request.user)})
