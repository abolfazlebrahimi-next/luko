import { useState } from 'react';
import {
  HiOutlineEye,
  HiOutlineEyeSlash,
  HiOutlineKey,
  HiOutlineLockClosed,
  HiOutlineNoSymbol,
  HiOutlineShieldCheck,
  HiOutlineUserGroup,
} from 'react-icons/hi2';
import { apiError } from '../../settingsApi';
import { useChangePassword, usePasswordStatus } from '../../useSettings';
import { ChildAccountCard } from '../children/ChildAccountCard';
import { PhoneVerifyCard } from '../verify/PhoneVerifyCard';
import { BAZAAR_BUILD } from '@/features/billing/bazaar';
import { childName, useSettingsEnv } from './SettingsContext';
import form from './form.module.css';
import styles from './PrivacyPage.module.css';

const PROMISES = [
  { icon: HiOutlineLockClosed, text: 'نوشته‌های «صندوقچه‌ی رازها» روی دستگاهِ خودِ فرزند رمزنگاری می‌شوند؛ هیچ‌کس، حتی شما و تیمِ لوکو، آن‌ها را نمی‌بیند.' },
  { icon: HiOutlineUserGroup, text: 'هر والد فقط گزارشِ فرزندانِ وصل به حسابِ خودش را می‌بیند و هر وقت بخواهد دسترسی را قطع می‌کند.' },
  { icon: HiOutlineNoSymbol, text: 'به بچه‌ها تبلیغ نشان نمی‌دهیم و اطلاعاتِ شما و فرزندتان را به هیچ شرکتی نمی‌دهیم.' },
  { icon: HiOutlineShieldCheck, text: BAZAAR_BUILD
    ? 'رمزها رمزنگاری‌شده نگه داشته می‌شوند و خریدِ اشتراک از راهِ کافه‌بازار است؛ اطلاعاتِ پرداخت به لوکو نمی‌رسد.'
    : 'رمزها رمزنگاری‌شده نگه داشته می‌شوند و پرداخت فقط از درگاهِ شاپرک است؛ اطلاعاتِ کارت به لوکو نمی‌رسد.' },
];

/** حریم خصوصی و امنیت: رمز و شماره‌ی والد، رمز و شماره‌ی هر فرزند، و تعهدهای لوکو */
export function PrivacyPage() {
  const env = useSettingsEnv();
  return (
    <div className={styles.page}>
      <section className={form.card} data-area="password" aria-labelledby="pw-title">
        <h3 id="pw-title" className={form.cardTitle}>رمزِ حسابِ شما</h3>
        <p className={form.cardNote}>اگر کدِ پیامکی نرسید، با شماره و همین رمز وارد پنل می‌شوید.</p>
        {env.guest ? <p className={styles.guest}>در حالتِ نمایشی رمز عوض نمی‌شود.</p> : <PasswordForm />}
      </section>

      <section className={form.card} data-area="phone" aria-labelledby="phone-title">
        <h3 id="phone-title" className={form.cardTitle}>شماره‌ی موبایلِ شما</h3>
        <p className={styles.phone} dir="ltr">{env.parentPhone}</p>
        {env.guest ? <p className={styles.guest}>در حالتِ نمایشی شماره تأیید نمی‌شود.</p> : <PhoneVerifyCard />}
      </section>

      <section className={form.card} data-area="children" aria-labelledby="kids-title">
        <h3 id="kids-title" className={form.cardTitle}>رمز و شماره‌ی فرزندان</h3>
        <p className={form.cardNote}>پنلِ بچه عمداً «فراموشیِ رمز» ندارد؛ رمزِ هر فرزند را این‌جا می‌بینید یا عوض می‌کنید.</p>
        {env.childList.length === 0 && <p className={styles.guest}>هنوز فرزندی اضافه نکرده‌اید.</p>}
        {env.guest
          ? env.childList.map((child) => <p key={child.id} className={styles.guest}>{childName(child)}: در حالتِ نمایشی پنهان است.</p>)
          : env.childList.map((child) => <ChildAccountCard key={child.id} child={child} onDone={env.onNotice} />)}
      </section>

      <section className={form.card} data-area="promises" aria-labelledby="promise-title">
        <h3 id="promise-title" className={form.cardTitle}>تعهدِ لوکو به حریمِ خصوصیِ خانواده</h3>
        <ul className={styles.promises}>
          {PROMISES.map(({ icon: Icon, text }) => (
            <li key={text}><Icon aria-hidden /><span>{text}</span></li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function PasswordForm() {
  const env = useSettingsEnv();
  const status = usePasswordStatus();
  const change = useChangePassword();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const has = status.data?.hasPassword ?? true;

  const submit = () => {
    setError('');
    if (next.length < 6) return setError('رمزِ تازه دست‌کم ۶ نویسه باشد.');
    if (next !== repeat) return setError('تکرارِ رمز با خودش یکی نیست.');
    if (has && !current) return setError('رمزِ فعلی را بنویسید.');
    change.mutate(
      { current: has ? current : undefined, password: next },
      {
        onSuccess: () => {
          setCurrent(''); setNext(''); setRepeat('');
          env.onNotice(has ? 'رمزِ شما عوض شد' : 'رمزِ شما ساخته شد');
        },
        onError: (err) => setError(apiError(err, 'رمز عوض نشد؛ دوباره تلاش کنید.')),
      },
    );
    return undefined;
  };

  const type = show ? 'text' : 'password';
  return (
    <div>
      {error && <p className={form.error} role="alert">{error}</p>}
      {has && (
        <label className={form.field}>
          رمزِ فعلی
          <input type={type} value={current} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
        </label>
      )}
      <label className={form.field}>
        رمزِ تازه
        <input type={type} value={next} autoComplete="new-password" onChange={(e) => setNext(e.target.value)} placeholder="دست‌کم ۶ نویسه" />
      </label>
      <label className={form.field}>
        تکرارِ رمزِ تازه
        <input type={type} value={repeat} autoComplete="new-password" onChange={(e) => setRepeat(e.target.value)} />
      </label>
      <div className={form.row}>
        <button type="button" className={form.primary} disabled={change.isPending} onClick={submit}>
          <HiOutlineKey aria-hidden /> {change.isPending ? 'در حالِ ذخیره…' : has ? 'تغییرِ رمز' : 'ساختنِ رمز'}
        </button>
        <button type="button" className={form.ghost} onClick={() => setShow((v) => !v)} aria-pressed={show}>
          {show ? <HiOutlineEyeSlash aria-hidden /> : <HiOutlineEye aria-hidden />} {show ? 'پنهان کردن' : 'نمایشِ رمز'}
        </button>
      </div>
    </div>
  );
}
