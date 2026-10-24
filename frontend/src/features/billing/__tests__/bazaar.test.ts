import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Win = {
  LukoBazaarNative?: Record<string, (...args: string[]) => unknown>;
  __lukoBazaar?: { onResult: (result: unknown) => void };
  setTimeout: typeof setTimeout;
  clearTimeout: typeof clearTimeout;
};

/** پلِ اندرویدِ ساختگی: مثلِ JavascriptInterfaceِ واقعی نتیجه را بعداً با window.__lukoBazaar.onResult می‌دهد */
function stubNative(win: Win, reply: (method: string, args: string[]) => object | null) {
  const calls: Array<[string, string[]]> = [];
  const respond = (method: string) => (...args: string[]) => {
    calls.push([method, args]);
    const requestId = args[args.length - 1];
    const result = reply(method, args);
    if (result) setTimeout(() => win.__lukoBazaar?.onResult(JSON.stringify({ requestId, ...result })), 0);
  };
  win.LukoBazaarNative = {
    isAvailable: () => 'true',
    subscribe: respond('subscribe'),
    getPurchasedSubscriptions: respond('getPurchasedSubscriptions'),
  };
  return calls;
}

describe('پلِ پرداختِ کافه‌بازار', () => {
  let win: Win;
  beforeEach(() => {
    vi.resetModules();
    win = { setTimeout, clearTimeout };
    vi.stubGlobal('window', win);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('بی پلِ اندروید (سایت یا نسخه‌ی قدیمیِ اپ) خرید ممکن نیست', async () => {
    const bazaar = await import('../bazaar');
    expect(bazaar.BAZAAR_BUILD).toBe(false);
    expect(bazaar.bazaarAvailable()).toBe(false);
    await expect(bazaar.bazaarSubscribe('luko_monthly', 'p')).rejects.toThrow('این نسخه‌ی اپ');
  });

  it('خرید: SKU و payload به اپ می‌رود و توکنِ خرید برمی‌گردد', async () => {
    const bazaar = await import('../bazaar');
    const calls = stubNative(win, () => ({ ok: true, purchase: { productId: 'luko_yearly', purchaseToken: 'TOK', orderId: 'O1' } }));
    expect(bazaar.bazaarAvailable()).toBe(true);
    const payload = bazaar.purchasePayload('42', 'yearly');
    const purchase = await bazaar.bazaarSubscribe('luko_yearly', payload);
    expect(purchase).toEqual({ productId: 'luko_yearly', purchaseToken: 'TOK', orderId: 'O1' });
    expect(calls[0][0]).toBe('subscribe');
    expect(calls[0][1].slice(0, 2)).toEqual(['luko_yearly', 'luko:42:yearly']);
    expect(bazaar.parsePayload(payload)).toEqual({ childId: '42', plan: 'yearly' });
  });

  it('لغو با خطا فرق دارد؛ نتیجه‌ی درخواستِ دیگر قاطی نمی‌شود', async () => {
    const bazaar = await import('../bazaar');
    stubNative(win, () => ({ ok: false, cancelled: true }));
    const cancelled = await bazaar.bazaarSubscribe('luko_monthly', 'p').catch((e) => e);
    expect(cancelled).toBeInstanceOf(bazaar.BazaarError);
    expect(cancelled.cancelled).toBe(true);

    stubNative(win, () => ({ ok: false, error: 'بازار نصب نیست' }));
    const failed = await bazaar.bazaarSubscribe('luko_monthly', 'p').catch((e) => e);
    expect(failed.message).toBe('بازار نصب نیست');
    expect(failed.cancelled).toBe(false);

    // پاسخِ بی‌صاحب یا خراب نادیده گرفته می‌شود
    win.__lukoBazaar?.onResult('{"requestId":"nobody","ok":true}');
    win.__lukoBazaar?.onResult('not json');
  });

  it('بازیابی: فقط خریدهای توکن‌دار؛ payloadِ بیگانه شناخته نمی‌شود', async () => {
    const bazaar = await import('../bazaar');
    stubNative(win, () => ({ ok: true, purchases: [{ productId: 'luko_monthly', purchaseToken: 'A', payload: 'luko:7:monthly' }, { productId: 'x' }] }));
    const list = await bazaar.bazaarPurchases();
    expect(list.map((p) => p.purchaseToken)).toEqual(['A']);
    expect(bazaar.parsePayload('other:7:monthly')).toBeNull();
    expect(bazaar.parsePayload(undefined)).toBeNull();
  });
});
