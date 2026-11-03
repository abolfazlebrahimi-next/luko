"""Referral attribution and redeemable, auditable subscription credits."""
import secrets

from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.billing.models import Payment
from apps.billing.services import CheckoutError, gift_subscription, lifetime_access
from .models import ParentChild, Referral, ReferralCode, ReferralReward
from .permissions import IsParent


def attribute_new_parent(user, code):
    """Called only as part of creation of a phone-verified parent."""
    if not code or user.role != User.Role.PARENT:
        return
    owner = ReferralCode.objects.select_related("parent").filter(code=code, parent__is_active=True,
                                                                 parent__role=User.Role.PARENT).first()
    if not owner or owner.parent_id == user.pk or owner.parent.phone == user.phone:
        return
    referral = Referral.objects.create(referrer=owner.parent, referred=user)
    ReferralReward.objects.bulk_create([
        ReferralReward(referral=referral, recipient=owner.parent, kind=ReferralReward.Kind.REFERRER_JOIN, days=3),
        ReferralReward(referral=referral, recipient=user, kind=ReferralReward.Kind.REFERRED_JOIN, days=3),
    ])


def reward_purchase(payment):
    """Only verified gateway purchases count; caller holds its payment transaction."""
    if payment.source != Payment.Source.GATEWAY or payment.status != Payment.Status.PAID or not payment.payer_id or payment.amount_toman <= 0:
        return
    referral = Referral.objects.select_for_update().filter(referred_id=payment.payer_id).first()
    if referral and referral.referrer_id and referral.first_purchase_id is None:
        referral.first_purchase = payment
        referral.save(update_fields=["first_purchase", "updated_at"])
        ReferralReward.objects.create(referral=referral, recipient=referral.referrer,
                                      kind=ReferralReward.Kind.PURCHASE, days=15)


class ReferralView(APIView):
    permission_classes = [IsParent]

    def get(self, request):
        if request.user.role != User.Role.PARENT:
            return Response(status=403)
        code, _ = ReferralCode.objects.get_or_create(parent=request.user, defaults={"code": secrets.token_urlsafe(24)})
        rewards = request.user.referral_rewards.order_by("-created_at")
        return Response({"code": code.code, "invitedCount": request.user.referrals_sent.count(),
                         "rewards": [{"id": r.pk, "kind": r.kind, "days": r.days,
                                      "redeemed": r.payment_id is not None} for r in rewards]})


class RedeemReferralRewardView(APIView):
    permission_classes = [IsParent]

    @transaction.atomic
    def post(self, request, reward_id):
        reward = ReferralReward.objects.select_for_update().filter(pk=reward_id, recipient=request.user).first()
        if not reward:
            return Response({"error": {"message": "پاداش پیدا نشد."}}, status=404)
        if reward.payment_id:
            return Response({"error": {"message": "این پاداش قبلاً استفاده شده است."}}, status=409)
        child_id = request.data.get("childId") or request.data.get("child_id")
        if not str(child_id or "").isdigit():
            return Response({"error": {"message": "فرزند را انتخاب کنید."}}, status=400)
        link = ParentChild.objects.select_for_update().select_related("child").filter(parent=request.user, child_id=child_id, is_active=True).first()
        if not link or link.child.role != User.Role.STUDENT:
            return Response({"error": {"message": "فرزند انتخاب‌شده در دسترس نیست."}}, status=400)
        if lifetime_access(link.child):
            return Response({"error": {"message": "این فرزند اشتراک همیشگی دارد؛ فرزند دیگری انتخاب کنید."}}, status=400)
        try:
            reward.payment = gift_subscription(child=link.child, days=reward.days, granted_by=request.user,
                                               note=f"پاداش معرفی {reward.pk}")
        except CheckoutError as exc:
            return Response({"error": {"message": str(exc)}}, status=400)
        reward.save(update_fields=["payment", "updated_at"])
        return Response({"redeemed": True})
