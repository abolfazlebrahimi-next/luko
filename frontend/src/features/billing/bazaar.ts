/**
 * خریدِ اشتراک از داخلِ اپِ اندرویدِ کافه‌بازار.
 *
 * قانونِ بازار: اپی که در بازار منتشر می‌شود اشتراک را فقط با پرداختِ درون‌برنامه‌ایِ بازار می‌فروشد — نه درگاهِ
 * دیگر، نه پیوند به سایت برای خرید. بیلدِ اپِ والدین با `VITE_STORE=bazaar` ساخته می‌شود؛ آن‌جا دکمه‌ی خرید به جای
 * زیبال این پل را صدا می‌زند. سمتِ اندروید (اسکچور) یک JavascriptInterface به نامِ `LukoBazaarNative` است که با
 * Poolakey خرید می‌کند و نتیجه را با `window.__lukoBazaar.onResult(json)` برمی‌گرداند (کدِ مرجع در README
 * بیلدِ اندروید). توکنِ خرید را سرور با APIِ بازار تأیید می‌کند (/billing/bazaar/verify)؛ به گفته‌ی اپ اعتماد نمی‌شود.
 */

/** بیلدِ اپِ کافه‌بازار؛ در سایت همیشه false */
export const BAZAAR_BUILD = import.meta.env.VITE_STORE === 'bazaar';

export interface BazaarPurchase {
  productId: string;
  purchaseToken: string;
  orderId?: string;
  payload?: string;
}

interface NativeBridge {
  isAvailable?: () => boolean | string;
  subscribe: (sku: string, payload: string, requestId: string) => void;
  getPurchasedSubscriptions: (requestId: string) => void;
}

interface BridgeResult {
  requestId: string;
  ok: boolean;
  /** خریدار برگه‌ی بازار را بست */
  cancelled?: boolean;
  error?: string;
  purchase?: BazaarPurchase;
  purchases?: BazaarPurchase[];
}

declare global {
  interface Window {
    LukoBazaarNative?: NativeBridge;
    __lukoBazaar?: { onResult: (result: string | BridgeResult) => void };
  }
}

export class BazaarError extends Error {
  readonly cancelled: boolean;

  constructor(message: string, cancelled = false) {
    super(message);
    this.cancelled = cancelled;
  }
}

/** بی پاسخ از سمتِ اندروید (اتصال به بازار گیر کرد) بعد از این مدت خطا می‌دهیم */
const TIMEOUT_MS = 5 * 60 * 1000;
const pending = new Map<string, (result: BridgeResult) => void>();
let counter = 0;

function native(): NativeBridge | undefined {
  return typeof window === 'undefined' ? undefined : window.LukoBazaarNative;
}

function install() {
  if (typeof window === 'undefined' || window.__lukoBazaar) return;
  window.__lukoBazaar = {
    onResult(raw) {
      let result: BridgeResult;
      try {
        result = typeof raw === 'string' ? JSON.parse(raw) : raw;
      } catch {
        return;
      }
      const resolve = pending.get(result?.requestId);
      if (!resolve) return;
      pending.delete(result.requestId);
      resolve(result);
    },
  };
}

/** اپِ اندروید پلِ پرداختِ بازار را دارد (و بازار روی گوشی نصب است) */
export function bazaarAvailable(): boolean {
  const bridge = native();
  if (!bridge || typeof bridge.subscribe !== 'function') return false;
  if (typeof bridge.isAvailable !== 'function') return true;
  const value = bridge.isAvailable();
  return value === true || value === 'true';
}

function call(run: (bridge: NativeBridge, requestId: string) => void): Promise<BridgeResult> {
  const bridge = native();
  if (!bridge) return Promise.reject(new BazaarError('پرداختِ کافه‌بازار در این نسخه‌ی اپ نیست.'));
  install();
  counter += 1;
  const requestId = `bz${Date.now()}-${counter}`;
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      pending.delete(requestId);
      reject(new BazaarError('کافه‌بازار جواب نداد؛ دوباره تلاش کنید.'));
    }, TIMEOUT_MS);
    pending.set(requestId, (result) => {
      window.clearTimeout(timer);
      resolve(result);
    });
    try {
      run(bridge, requestId);
    } catch {
      window.clearTimeout(timer);
      pending.delete(requestId);
      reject(new BazaarError('باز کردنِ کافه‌بازار انجام نشد.'));
    }
  });
}

/** شناسه‌ی فرزند و پلن همراهِ خرید در بازار می‌ماند تا بازیابیِ خرید بداند مالِ کدام بچه است */
export function purchasePayload(childId: string, plan: string): string {
  return `luko:${childId}:${plan}`;
}

export function parsePayload(payload?: string): { childId: string; plan: string } | null {
  const match = /^luko:([^:]+):([a-z0-9_-]+)$/.exec(payload ?? '');
  return match ? { childId: match[1], plan: match[2] } : null;
}

export async function bazaarSubscribe(sku: string, payload: string): Promise<BazaarPurchase> {
  const result = await call((bridge, id) => bridge.subscribe(sku, payload, id));
  if (result.ok && result.purchase?.purchaseToken) return result.purchase;
  if (result.cancelled) throw new BazaarError('خرید لغو شد.', true);
  throw new BazaarError(result.error || 'خرید از کافه‌بازار انجام نشد؛ دوباره تلاش کنید.');
}

/** اشتراک‌هایی که این حسابِ بازار خریده (بازیابی: پاسخِ سرور بعد از خرید گم شده بود، یا گوشیِ تازه) */
export async function bazaarPurchases(): Promise<BazaarPurchase[]> {
  const result = await call((bridge, id) => bridge.getPurchasedSubscriptions(id));
  if (!result.ok) throw new BazaarError(result.error || 'فهرستِ خریدها از کافه‌بازار نیامد.');
  return (result.purchases ?? []).filter((p) => p?.purchaseToken);
}
