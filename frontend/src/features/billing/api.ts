import { apiClient } from '@/lib/api';
import type { BazaarVerifyResult, CheckoutResult, ChildSubscription, Payment, Plan } from './types';

/** APIهای اشتراک؛ پاکتِ {data} همین‌جا باز می‌شود. */
export const billingApi = {
  async plans(): Promise<Plan[]> {
    const { data } = await apiClient.get('/billing/plans');
    return data.data;
  },

  async children(): Promise<ChildSubscription[]> {
    const { data } = await apiClient.get('/billing/children');
    return data.data;
  },

  async payments(childId?: string): Promise<Payment[]> {
    const { data } = await apiClient.get('/billing/payments', {
      params: childId ? { child: childId } : undefined,
    });
    return data.data;
  },

  /** `refresh` پرداختِ در انتظار را همان لحظه با درگاه پیگیری می‌کند (صفحه‌ی نتیجه) */
  async payment(id: number, refresh = false): Promise<Payment> {
    const { data } = await apiClient.get(`/billing/payments/${id}`, {
      params: refresh ? { refresh: 1 } : undefined,
    });
    return data.data;
  },

  async checkout(childId: string, plan: string): Promise<CheckoutResult> {
    const { data } = await apiClient.post('/billing/checkout', { childId, plan });
    return data.data;
  },

  /** خریدِ اپِ کافه‌بازار → سرور با APIِ بازار تأیید می‌کند → اشتراکِ همان فرزند */
  async verifyBazaar(childId: string, plan: string, purchaseToken: string, orderId = ''): Promise<BazaarVerifyResult> {
    const { data } = await apiClient.post('/billing/bazaar/verify', { childId, plan, purchaseToken, orderId });
    return data.data;
  },
};
