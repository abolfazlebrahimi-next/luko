import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  HiOutlineCheck,
  HiOutlineCheckCircle,
  HiOutlineChevronDown,
  HiOutlineClock,
  HiOutlineDocumentText,
  HiOutlineExclamationTriangle,
  HiOutlineMinus,
  HiOutlineShieldCheck,
  HiOutlineXCircle,
} from 'react-icons/hi2';
import { CrownIcon } from '@/components/ui/icons';
import { apiMessage, faNumber, toman } from '@/features/billing/format';
import type { ChildSubscription, Payment, Plan } from '@/features/billing/types';
import { BAZAAR_BUILD, BazaarError, bazaarAvailable } from '@/features/billing/bazaar';
import { useBazaarPurchase, useBazaarRestore, useCheckout, usePayments, usePlans } from '@/features/billing/useBilling';
import { Sheet } from '../shell/Sheet';
import { TrustSeals } from './TrustSeals';
import { childName, useSettingsEnv } from './SettingsContext';
import form from './form.module.css';
import styles from './BillingPage.module.css';

/** همان دو پلنِ سرور — فقط برای مهمان که API ندارد */
const GUEST_PLANS: Plan[] = [
  { code: 'monthly', title: 'ماهانه', durationDays: 30, months: 1, priceToman: 199_000, perMonthToman: 199_000, savingPercent: 0 },
  { code: 'yearly', title: 'سالانه', durationDays: 365, months: 12, priceToman: 1_499_000, perMonthToman: 124_917, savingPercent: 37 },
];
const NO_PLANS: Plan[] = [];

/** آن‌چه با اشتراک باز می‌شود — همان قفل‌های پنل (apps/parent/gating.py) */
const COMPARE: { label: string; free: string | boolean; premium: string | boolean }[] = [
  { label: 'گزارشِ هفتگیِ خودکار', free: true, premium: true },
  { label: 'وضعیتِ درسِ ریاضی', free: true, premium: true },
  { label: 'وضعیت و آمارِ همه‌ی درس‌ها', free: false, premium: true },
  { label: 'پیشنهادهای شخصیِ هر هفته', free: 'فقط یکی', premium: 'همه' },
  { label: 'حالِ کلیِ هفته', free: true, premium: true },
  { label: 'حالِ دقیقِ روزانه، درس‌ها و علاقه‌ها', free: false, premium: true },
  { label: 'پاسخِ اولویت‌دارِ پشتیبانی', free: false, premium: true },
];

/** شماره‌ها و کارت چپ‌به‌راست خوانده می‌شوند */
const LTR = new Set(['شماره‌ی فاکتور', 'کدِ پیگیری', 'کارت']);

const PAY_ICON = { paid: HiOutlineCheckCircle, failed: HiOutlineXCircle, expired: HiOutlineClock, pending: HiOutlineClock };

/** اشتراک و پرداخت‌ها برای هر فرزند: وضعیت، تمدید، پلن‌ها، مقایسه و صورت‌حساب‌ها */
export function BillingPage() {
  const env = useSettingsEnv();
  const [params, setParams] = useSearchParams();
  const plansQuery = usePlans(!env.guest);
  const plans = useMemo(() => (env.guest ? GUEST_PLANS : (plansQuery.data ?? NO_PLANS)), [env.guest, plansQuery.data]);
  const child = env.childList.find((item) => item.id === env.activeChildId) ?? env.childList[0];
  const sub = env.subscriptions?.find((item) => item.childId === child?.id);
  const payments = usePayments(child?.id, !env.guest && Boolean(child));
  const name = childName(child);
  const shortName = child?.firstName?.trim() || name;

  const wanted = params.get('plan');
  const [selected, setSelected] = useState<string | null>(null);
  /** پلنی که همین حالا به درگاهش می‌رویم (برای نوشته‌ی همان دکمه) */
  const [paying, setPaying] = useState<string | null>(null);
  const [loginSheet, setLoginSheet] = useState(false);
  const checkout = useCheckout();
  const bazaarBuy = useBazaarPurchase();
  /** اپِ کافه‌بازار: خرید فقط با پرداختِ بازار (قانونِ بازار)؛ بی پلِ اندروید خرید ممکن نیست */
  const canBuyInApp = !BAZAAR_BUILD || env.guest || bazaarAvailable();
  const childIds = useMemo(() => env.childList.map((item) => item.id), [env.childList]);
  useBazaarRestore(BAZAAR_BUILD && !env.guest, plans, childIds);
  const invoiceRef = useRef<HTMLElement>(null);

  const sorted = useMemo(() => [...plans].sort((a, b) => a.durationDays - b.durationDays), [plans]);
  const fallback = wanted ?? sub?.renewal?.planCode ?? plans.find((p) => p.savingPercent > 0)?.code ?? plans[0]?.code;
  const activePlan = plans.find((p) => p.code === (selected ?? fallback));

  // از اعلانِ «رو به پایان» آمده: صورت‌حساب جلوی چشم (دکمه‌اش مستقیم به درگاه می‌رود)
  useEffect(() => {
    if (!sub || !wanted) return;
    invoiceRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    if (params.get('pay') === '1') {
      const next = new URLSearchParams(params);
      next.delete('pay');
      setParams(next, { replace: true });
    }
    // فقط بارِ اولِ رسیدنِ داده
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sub?.childId]);

  /**
   * «خرید»/«تمدید» مستقیم به درگاه می‌رود (۲۶ مهر ۱۴۰۵، خواستِ کاربر: برگه‌ی «تأیید و پرداخت» فقط معطلی بود؛
   * پلن، مبلغ و فرزند همان روی دکمه و صورت‌حساب پیداست و درگاه هم مبلغ را پیش از پرداخت نشان می‌دهد).
   */
  const pay = (code: string) => {
    if (env.guest) {
      setLoginSheet(true);
      return;
    }
    if (BAZAAR_BUILD) {
      const plan = plans.find((p) => p.code === code);
      if (bazaarBuy.isPending || !plan) return;
      setPaying(code);
      bazaarBuy.mutate({ childId: child!.id, plan });
      return;
    }
    if (checkout.isPending || checkout.isSuccess) return;
    setPaying(code);
    checkout.mutate({ childId: child!.id, plan: code });
  };
  const going = BAZAAR_BUILD ? bazaarBuy.isPending : checkout.isPending || checkout.isSuccess;
  const goingLabel = BAZAAR_BUILD ? 'در حالِ خرید از کافه‌بازار…' : 'در حالِ انتقال به درگاه…';
  const payError = BAZAAR_BUILD
    ? bazaarBuy.isError && !(bazaarBuy.error instanceof BazaarError && bazaarBuy.error.cancelled)
      ? <p className={form.error} role="alert">{bazaarBuy.error instanceof BazaarError ? bazaarBuy.error.message
        : apiMessage(bazaarBuy.error, 'خرید انجام شد ولی تأییدش نرسید؛ چند دقیقه‌ی دیگر همین صفحه را دوباره باز کنید.')}</p>
      : null
    : checkout.isError
      ? <p className={form.error} role="alert">{apiMessage(checkout.error, 'رفتن به درگاه انجام نشد؛ دوباره تلاش کنید.')}</p>
      : null;
  /** اشتراکِ فعالِ کافه‌بازار خودش تمدید می‌شود؛ خریدِ دوباره (از سایت یا اپ) پولِ دوباره است */
  const autoRenews = Boolean(sub?.autoRenews);
  /** در اپِ بازار دوره‌ی بازار از روزِ خرید شروع می‌شود، پس تا اشتراکِ فعلی رو به پایان نیست خرید بسته است */
  const buyLocked = autoRenews || (BAZAAR_BUILD && sub?.status === 'active' && !sub.expiringSoon);

  if (!child) {
    return (
      <div className={styles.empty}>
        <b>هنوز فرزندی اضافه نکرده‌اید</b>
        <p>اشتراک برای هر فرزند جداست؛ اول فرزندتان را اضافه کنید.</p>
        <button type="button" className={form.primary} onClick={env.onAddChild}>افزودنِ فرزند</button>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {env.childList.length > 1 && (
        <div className={styles.kids} role="tablist" aria-label="اشتراکِ کدام فرزند">
          {env.childList.map((item) => {
            const s = env.subscriptions?.find((row) => row.childId === item.id);
            const on = item.id === child.id;
            return (
              <button key={item.id} type="button" role="tab" aria-selected={on} data-active={on || undefined}
                onClick={() => { setSelected(null); env.onChildChange(item.id); }}>
                <i aria-hidden>{childName(item).charAt(0)}</i>
                <span><b>{childName(item)}</b><small>{s?.lifetime ? 'اشتراکِ همیشگی' : s?.status === 'active' ? `${faNumber(s.daysLeft)} روز اشتراک` : 'پلنِ رایگان'}</small></span>
              </button>
            );
          })}
        </div>
      )}

      <div className={styles.top}>
        <StatusHero sub={sub} name={name} />

        {sub?.renewal && !buyLocked ? (
          <section ref={invoiceRef} className={styles.invoice} data-urgent={sub.status === 'free' || sub.expiringSoon || undefined}
            aria-label="صورت‌حسابِ تمدید">
            <header>
              <HiOutlineDocumentText aria-hidden />
              <b>صورت‌حسابِ تمدید</b>
              <em>{sub.status === 'free' ? 'سررسید گذشته' : sub.expiringSoon ? 'سررسید نزدیک' : 'پیشنهادی'}</em>
            </header>
            <dl>
              <div><dt>پلن</dt><dd>اشتراکِ {sub.renewal.planTitle}</dd></div>
              <div><dt>برای</dt><dd>{name}</dd></div>
              <div><dt>شروع از</dt><dd>{sub.status === 'active' ? sub.renewal.startsFromFa : 'امروز'}</dd></div>
              <div data-total><dt>مبلغ</dt><dd>{toman(sub.renewal.amountToman)}</dd></div>
            </dl>
            {paying === sub.renewal.planCode && payError}
            <button type="button" className={form.primary} disabled={going || !canBuyInApp} onClick={() => pay(sub.renewal!.planCode)}>
              {going && paying === sub.renewal.planCode ? goingLabel : BAZAAR_BUILD ? 'تمدید با کافه‌بازار' : 'پرداخت و تمدید'}
            </button>
          </section>
        ) : (
          <section className={styles.compare} aria-labelledby="compare-title">
            <h3 id="compare-title">با اشتراک چه چیزهایی باز می‌شود؟</h3>
            <CompareTable />
          </section>
        )}
      </div>

      <section className={form.card} aria-labelledby="plans-title">
        <h3 id="plans-title" className={form.cardTitle}>پلن‌های اشتراکِ {shortName}</h3>
        <div className={styles.plans} role="radiogroup" aria-label="انتخابِ پلن">
          {sorted.map((plan) => {
            const on = activePlan?.code === plan.code;
            return (
              <button key={plan.code} type="button" role="radio" aria-checked={on} className={styles.plan}
                data-selected={on || undefined} data-best={plan.savingPercent > 0 || undefined} onClick={() => setSelected(plan.code)}>
                {plan.savingPercent > 0 && <span className={styles.ribbon}>به‌صرفه‌ترین · {faNumber(plan.savingPercent)}٪ ارزان‌تر</span>}
                <span className={styles.radio} aria-hidden />
                <span className={styles.planName}>{plan.title}</span>
                <span className={styles.price}><b>{faNumber(plan.priceToman)}</b><small>تومان</small></span>
                <span className={styles.per}>{plan.months > 1 ? `ماهی حدودِ ${faNumber(plan.perMonthToman)} تومان` : 'هر ماه'} · {faNumber(plan.durationDays)} روز</span>
              </button>
            );
          })}
        </div>
        {activePlan && paying === activePlan.code && payError}
        {sub?.lifetime && <p className={styles.hint}>اشتراکِ {shortName} همیشگی است؛ خرید یا تمدید لازم نیست.</p>}
        {autoRenews && !sub?.lifetime && (
          <p className={styles.hint}>
            اشتراکِ {shortName} از کافه‌بازار است و هر دوره خودکار تمدید می‌شود؛ خریدِ دوباره لازم نیست. لغوِ تمدید از
            بخشِ «اشتراک‌ها»ی کافه‌بازار است.
          </p>
        )}
        {BAZAAR_BUILD && !autoRenews && buyLocked && !sub?.lifetime && (
          <p className={styles.hint}>اشتراکِ فعلیِ {shortName} تا {sub?.endsAtFa} فعال است؛ تمدید از یک هفته پیش از پایانش باز می‌شود.</p>
        )}
        {activePlan && !sub?.lifetime && !buyLocked && (
          <button type="button" className={form.primary} disabled={going || !canBuyInApp} onClick={() => pay(activePlan.code)}>
            <CrownIcon size={18} strokeWidth={2} aria-hidden />
            {going && paying === activePlan.code ? goingLabel
              : `${sub?.status === 'active' ? 'تمدید با' : 'خریدِ'} اشتراکِ ${activePlan.title}، ${toman(activePlan.priceToman)}`}
          </button>
        )}
        {!canBuyInApp && !buyLocked && !sub?.lifetime && (
          <p className={styles.hint}>خرید در این نسخه‌ی اپ ممکن نیست؛ اپ را از کافه‌بازار به‌روز کنید و مطمئن شوید کافه‌بازار روی گوشی نصب است.</p>
        )}
        {BAZAAR_BUILD && !buyLocked && !sub?.lifetime && canBuyInApp && (
          <p className={styles.hint}>
            پرداخت با کافه‌بازار است. اشتراک از روزِ خرید شروع می‌شود و در پایانِ هر دوره با همین مبلغ خودکار تمدید
            می‌شود؛ هر وقت بخواهید از بخشِ «اشتراک‌ها»ی کافه‌بازار لغوش می‌کنید و تا پایانِ دوره‌ی پرداخت‌شده فعال می‌ماند.
          </p>
        )}
        {!BAZAAR_BUILD && sub?.status === 'active' && !sub.lifetime && !autoRenews && <p className={styles.hint}>تمدید پشتِ اشتراکِ فعلی می‌نشیند؛ روزهای باقی‌مانده از دست نمی‌رود.</p>}
        {sub?.renewal && (
          <details className={styles.compareMore}>
            <summary>با اشتراک چه چیزهایی باز است؟ <HiOutlineChevronDown aria-hidden /></summary>
            <CompareTable />
          </details>
        )}
      </section>

      <section className={form.card} aria-labelledby="history-title">
        <h3 id="history-title" className={form.cardTitle}>صورت‌حساب‌ها و پرداخت‌ها</h3>
        {env.guest || (payments.data?.length ?? 0) === 0 ? (
          <p className={styles.none}>{payments.isLoading ? 'در حالِ بارگذاری…' : `هنوز پرداختی برای ${shortName} ثبت نشده است.`}</p>
        ) : (
          <ul className={styles.history}>
            {payments.data?.map((payment) => <PaymentRow key={payment.id} payment={payment} />)}
          </ul>
        )}
      </section>

      {BAZAAR_BUILD ? (
        <div className={styles.trust}>
          <p><HiOutlineShieldCheck aria-hidden /> پرداخت از راهِ کافه‌بازار؛ اطلاعاتِ پرداخت به لوکو نمی‌رسد.</p>
        </div>
      ) : (
        <div className={styles.trust}>
          <p><HiOutlineShieldCheck aria-hidden /> پرداختِ امن با درگاهِ زیبال؛ پس از پرداخت به همین پنل برمی‌گردید.</p>
          <TrustSeals />
        </div>
      )}


      <Sheet open={loginSheet} title="ورود لازم است" onClose={() => setLoginSheet(false)}>
        <p className={styles.sheetText}>
          این پنل نمونه است. برای خریدِ اشتراک با شماره‌ی موبایلِ خودتان وارد شوید و فرزندتان را اضافه کنید.
        </p>
        <div className={form.row}>
          <button type="button" className={form.primary} onClick={() => { setLoginSheet(false); env.onLogout(); }}>ورود به حساب</button>
          <button type="button" className={form.ghost} onClick={() => setLoginSheet(false)}>بعداً</button>
        </div>
      </Sheet>
    </div>
  );
}

function StatusHero({ sub, name }: { sub?: ChildSubscription; name: string }) {
  if (!sub || sub.status === 'free') {
    return (
      <section className={styles.hero} data-tone="free">
        <span className={styles.freeMark} aria-hidden><CrownIcon size={30} /></span>
        <div>
          <span className={styles.chip}>پلنِ رایگان</span>
          <h2>{name}</h2>
          <p>ریاضی، گزارشِ هفتگی و حالِ کلیِ هفته باز است. با اشتراک، همه‌ی درس‌ها، حالِ دقیقِ روزانه و همه‌ی پیشنهادها باز می‌شود.</p>
        </div>
      </section>
    );
  }
  const r = 46;
  const c = 2 * Math.PI * r;
  // همیشگی: حلقه‌ی پر، بی‌شمارشِ روز
  const ratio = sub.lifetime ? 1 : sub.totalDays > 0 ? Math.min(1, Math.max(0.03, sub.daysLeft / sub.totalDays)) : 0;
  return (
    <section className={styles.hero} data-tone={sub.expiringSoon ? 'warn' : 'active'}>
      <div className={styles.ring}>
        <svg viewBox="0 0 108 108" aria-hidden>
          <circle className={styles.ringTrack} cx="54" cy="54" r={r} />
          <circle className={styles.ringValue} cx="54" cy="54" r={r} strokeDasharray={`${c * ratio} ${c}`} />
        </svg>
        {sub.lifetime
          ? <span><b>همیشه</b><small>فعال</small></span>
          : <span><b>{faNumber(sub.daysLeft)}</b><small>روز مانده</small></span>}
      </div>
      <div>
        <span className={styles.chip}><CrownIcon size={13} strokeWidth={2.2} aria-hidden /> اشتراکِ {sub.planTitle}</span>
        <h2>{name}</h2>
        <p>{sub.lifetime ? 'اشتراکِ کامل، بی‌تاریخِ پایان.' : `تا ${sub.endsAtFa} فعال است.`}</p>
        {sub.autoRenews && <p>با کافه‌بازار خودکار تمدید می‌شود.</p>}
        {sub.expiringSoon && (
          <p className={styles.warn}><HiOutlineExclamationTriangle aria-hidden /> کمتر از یک هفته مانده؛ برای قطع‌نشدن، تمدید کنید.</p>
        )}
      </div>
    </section>
  );
}

function CompareTable() {
  const cell = (value: string | boolean) =>
    typeof value === 'string' ? value : value ? <HiOutlineCheck aria-label="دارد" /> : <HiOutlineMinus aria-label="ندارد" />;
  return (
    <table className={styles.table}>
      <thead><tr><th scope="col">امکان</th><th scope="col">رایگان</th><th scope="col"><CrownIcon size={13} strokeWidth={2.2} aria-hidden /> اشتراک</th></tr></thead>
      <tbody>
        {COMPARE.map((row) => (
          <tr key={row.label}>
            <th scope="row">{row.label}</th>
            <td data-on={row.free !== false || undefined}>{cell(row.free)}</td>
            <td data-on={row.premium !== false || undefined}>{cell(row.premium)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PaymentRow({ payment }: { payment: Payment }) {
  const [open, setOpen] = useState(false);
  const Icon = PAY_ICON[payment.status] ?? HiOutlineClock;
  const rows: [string, string][] = [
    ['شماره‌ی فاکتور', payment.factorNumber],
    ['کدِ پیگیری', payment.transId],
    ['کارت', payment.cardNumber],
    ['پرداخت', payment.gateway === 'bazaar' ? 'کافه‌بازار' : ''],
    ['دوره', payment.status === 'paid' ? `${payment.startsAtFa} تا ${payment.endsAtFa}` : ''],
    ['ثبت', payment.createdAtFa],
    ['پیام', payment.message],
  ].filter(([, value]) => value) as [string, string][];
  return (
    <li className={styles.pay} data-status={payment.status}>
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className={styles.payIcon} aria-hidden><Icon /></span>
        <span className={styles.payMain}>
          <b>اشتراکِ {payment.planTitle}</b>
          <small>{payment.paidAtFa || payment.createdAtFa}</small>
        </span>
        <span className={styles.payEnd}>
          <b>{payment.isGift ? 'هدیه‌ی لوکو' : toman(payment.amountToman)}</b>
          <em>{payment.statusLabel}</em>
        </span>
        <HiOutlineChevronDown className={styles.payChev} aria-hidden />
      </button>
      {open && (
        <dl className={styles.payDetails}>
          {rows.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd dir={LTR.has(label) ? 'ltr' : undefined}>{value}</dd></div>
          ))}
        </dl>
      )}
    </li>
  );
}
