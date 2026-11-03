from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import Payment, Plan
from apps.billing.services import _activate, subscription
from apps.parent.models import ParentChild, Referral, ReferralCode, ReferralReward


class ReferralTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create(phone="09120000001", role=User.Role.PARENT)
        self.code = ReferralCode.objects.create(parent=self.parent, code="example-code")
        self.client = APIClient()

    def signup(self, phone, code="example-code"):
        with patch("apps.accounts.views.verify_otp", return_value=True):
            return self.client.post('/api/v1/auth/verify-otp', {
                'phone': phone, 'code': '12345', 'role': 'parent', 'referralCode': code,
            }, format='json')

    def test_signup_once_and_existing_not_attributed(self):
        res = self.signup('09120000002')
        self.assertEqual(res.status_code, 201)
        invitee = User.objects.get(phone='09120000002', role='parent')
        self.assertTrue(invitee.phone_verified)
        self.assertEqual(ReferralReward.objects.count(), 2)
        self.assertEqual(self.signup('09120000002').status_code, 200)
        self.assertEqual(ReferralReward.objects.count(), 2)
        User.objects.create(phone='09120000003', role='parent')
        self.signup('09120000003')
        self.assertEqual(Referral.objects.count(), 1)

    def test_invalid_and_self_code_ignored(self):
        self.signup('09120000004', 'invalid')
        self.signup(self.parent.phone)
        self.assertFalse(Referral.objects.exists())

    def test_redeem_is_authorized_and_single_use(self):
        self.signup('09120000002')
        reward = ReferralReward.objects.get(recipient=self.parent)
        child = User.objects.create(phone='09120000005', role='student')
        ParentChild.objects.create(parent=self.parent, child=child)
        other = User.objects.get(phone='09120000002', role='parent')
        self.client.force_authenticate(other)
        url = f'/api/v1/parent/referral/rewards/{reward.pk}/redeem'
        self.assertEqual(self.client.post(url, {'childId': child.pk}, format='json').status_code, 404)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.post(url, {'childId': 9999}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'childId': child.pk}, format='json').status_code, 200)
        self.assertEqual(subscription(child).days_left, 3)
        self.assertEqual(self.client.post(url, {'childId': child.pk}, format='json').status_code, 409)
        self.assertEqual(subscription(child).days_left, 3)

    def test_only_first_paid_purchase_rewards_referrer(self):
        self.signup('09120000002')
        invitee = User.objects.get(phone='09120000002', role='parent')
        child = User.objects.create(phone='09120000006', role='student')
        plan = Plan.objects.first()
        for n in range(2):
            payment = Payment.objects.create(payer=invitee, child=child, plan=plan, plan_title=plan.title,
                duration_days=plan.duration_days, amount_toman=plan.price_toman, amount_rial=plan.price_rial,
                factor_number=f'test{n}')
            _activate(payment, {})
        rewards = ReferralReward.objects.filter(kind='purchase')
        self.assertEqual(rewards.count(), 1)
        self.assertEqual((rewards.first().recipient, rewards.first().days), (self.parent, 15))

    def test_code_endpoint_is_stable_and_private(self):
        self.assertIn(self.client.get('/api/v1/parent/referral').status_code, (401, 403))
        self.client.force_authenticate(self.parent)
        result = self.client.get('/api/v1/parent/referral').json()['data']
        self.assertEqual(result['code'], self.code.code)
        self.assertEqual(result['invitedCount'], 0)

    def test_failed_otp_does_not_attribute(self):
        with patch('apps.accounts.views.verify_otp', return_value=False):
            response = self.client.post('/api/v1/auth/verify-otp', {
                'phone': '09120000008', 'code': '12345', 'role': 'parent', 'referralCode': self.code.code,
            }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Referral.objects.exists())

    def test_bazaar_verified_purchase_and_replay(self):
        from datetime import timedelta
        from django.test import override_settings
        from django.utils import timezone
        from apps.billing.services import verify_bazaar_purchase
        from apps.billing.bazaar import BazaarSubscription
        self.signup('09120000002')
        invitee = User.objects.get(phone='09120000002', role='parent')
        child = User.objects.create(phone='09120000009', role='student')
        plan = Plan.objects.first()
        now = timezone.now()
        sub = BazaarSubscription(started_at=now, valid_until=now + timedelta(days=30), auto_renewing=False, linked_token=None, raw={})
        with override_settings(BAZAAR_SKUS={plan.code: 'sku'}), patch('apps.billing.services._bazaar_check', return_value=sub):
            verify_bazaar_purchase(invitee, child, plan, 'purchase-token')
            verify_bazaar_purchase(invitee, child, plan, 'purchase-token')
        self.assertEqual(ReferralReward.objects.filter(kind='purchase', recipient=self.parent).count(), 1)
