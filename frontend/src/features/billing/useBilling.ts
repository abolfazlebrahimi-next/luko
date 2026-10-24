import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { billingApi } from './api';
import { bazaarAvailable, bazaarPurchases, bazaarSubscribe, parsePayload, purchasePayload } from './bazaar';
import type { Plan } from './types';
import { goToGateway } from './gateway';

const MINUTE = 60 * 1000;

export const billingKeys = {
  plans: ['billing', 'plans'] as const,
  children: ['billing', 'children'] as const,
  payments: (childId?: string) => ['billing', 'payments', childId ?? 'all'] as const,
  payment: (id: number) => ['billing', 'payment', id] as const,
};

export function usePlans(enabled = true) {
  return useQuery({ queryKey: billingKeys.plans, queryFn: billingApi.plans, staleTime: 10 * MINUTE, enabled });
}

/** وضعیتِ اشتراکِ همه‌ی فرزندان — نشانِ نوار و صفحه‌ی اشتراک */
export function useSubscriptions(enabled = true) {
  return useQuery({
    queryKey: billingKeys.children,
    queryFn: billingApi.children,
    staleTime: MINUTE,
    enabled,
  });
}

export function usePayments(childId?: string, enabled = true) {
  return useQuery({
    queryKey: billingKeys.payments(childId),
    queryFn: () => billingApi.payments(childId),
    staleTime: 30 * 1000,
    enabled,
  });
}

/** پرداخت را می‌سازد و مرورگر را به درگاه (زیبال؛ وندار اگر سرور آن را برگزیده باشد) می‌برد */
export function useCheckout() {
  return useMutation({
    mutationFn: ({ childId, plan }: { childId: string; plan: string }) => billingApi.checkout(childId, plan),
    onSuccess: (result) => goToGateway(result.payUrl),
  });
}

/**
 * خرید در اپِ کافه‌بازار: برگه‌ی پرداختِ بازار → توکنِ خرید → تأییدِ سرور. اگر پاسخِ سرور گم شود، خرید در
 * بازار هست و `useBazaarRestore` بارِ بعد دوباره می‌فرستدش.
 */
export function useBazaarPurchase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ childId, plan }: { childId: string; plan: Plan }) => {
      if (!plan.bazaarSku) throw new Error('این پلن در کافه‌بازار نیست.');
      const purchase = await bazaarSubscribe(plan.bazaarSku, purchasePayload(childId, plan.code));
      return billingApi.verifyBazaar(childId, plan.code, purchase.purchaseToken, purchase.orderId);
    },
    onSettled: () => client.invalidateQueries({ queryKey: ['billing'] }),
  });
}

/**
 * یک بار با بازشدنِ صفحه‌ی اشتراک: خریدهای بازارِ این گوشی را به سرور می‌دهد (تکرارش بی‌خطر است). خریدی که
 * تأییدش نرسیده بود فعال می‌شود و تمدید یا لغوِ تمدید در بازار همان لحظه دیده می‌شود.
 */
export function useBazaarRestore(enabled: boolean, plans: Plan[], childIds: string[]) {
  const client = useQueryClient();
  const done = useRef(false);
  const ready = enabled && plans.length > 0 && childIds.length > 0;
  useEffect(() => {
    if (!ready || done.current || !bazaarAvailable()) return;
    done.current = true;
    (async () => {
      let changed = false;
      for (const purchase of await bazaarPurchases().catch(() => [])) {
        const target = parsePayload(purchase.payload);
        const plan = plans.find((p) => p.bazaarSku === purchase.productId);
        if (!target || !plan || !childIds.includes(target.childId)) continue;
        try {
          await billingApi.verifyBazaar(target.childId, plan.code, purchase.purchaseToken, purchase.orderId);
          changed = true;
        } catch {
          // تمام‌شده، مالِ حسابِ دیگر، یا شبکه — دفعه‌ی بعد
        }
      }
      if (changed) client.invalidateQueries({ queryKey: ['billing'] });
    })();
  }, [ready, plans, childIds, client]);
}
