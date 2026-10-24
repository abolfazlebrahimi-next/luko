import { useState } from 'react';
import { HiOutlineChevronDown, HiOutlineEnvelope, HiOutlineGlobeAlt, HiOutlineHeart } from 'react-icons/hi2';
import { LukoLogo } from '@/components/ui/LukoLogo/LukoLogo';
import { BAZAAR_BUILD } from '@/features/billing/bazaar';
import { TrustSeals } from './TrustSeals';
import { useSettingsEnv } from './SettingsContext';
import form from './form.module.css';
import styles from './AboutPage.module.css';

const RULES: { title: string; body: string }[] = [
  {
    title: 'قوانینِ استفاده',
    body: 'حسابِ هر فرزند را والد یا سرپرستش می‌سازد و مسئولِ آن است. اشتراک برای هر فرزند جداست و از روزِ پرداخت (یا پایانِ اشتراکِ فعلی) شمرده می‌شود. استفاده از لوکو برای آزار یا فریبِ دیگران ممنوع است.',
  },
  {
    title: 'حریم خصوصی',
    body: 'گزارش‌های این پنل فقط از بازی‌ها و حال‌هایی ساخته می‌شوند که فرزندتان در لوکو ثبت کرده است. نوشته‌های «صندوقچه‌ی رازها» رمزنگاری‌شده‌اند. اطلاعاتِ شما و فرزندتان به هیچ شرکتی داده نمی‌شود و به بچه‌ها تبلیغ نشان داده نمی‌شود.',
  },
  {
    title: 'پرداخت و بازگشتِ وجه',
    body: BAZAAR_BUILD
      ? 'خریدِ اشتراک در این اپ از راهِ کافه‌بازار است و اطلاعاتِ پرداخت به لوکو نمی‌رسد. اشتراک در پایانِ هر دوره خودکار تمدید می‌شود و لغوِ تمدید از بخشِ «اشتراک‌ها»ی کافه‌بازار است؛ تا پایانِ دوره‌ی پرداخت‌شده فعال می‌ماند. اگر پرداخت انجام شد ولی اشتراک فعال نشد، صفحه‌ی اشتراک را دوباره باز کنید یا با دسته‌ی «اشتراک و پرداخت» تیکت بزنید.'
      : 'پرداخت از درگاهِ امنِ زیبال (شاپرک) انجام می‌شود و اطلاعاتِ کارت به لوکو نمی‌رسد. اگر پرداخت انجام شد ولی اشتراک فعال نشد، مبلغ طبقِ قوانینِ شاپرک برمی‌گردد یا اشتراک دستی فعال می‌شود؛ کافی است با دسته‌ی «اشتراک و پرداخت» تیکت بزنید.',
  },
];

/** درباره‌ی لوکو: معرفی، قوانین، نمادِ اعتماد و راه‌های تماس */
export function AboutPage() {
  const env = useSettingsEnv();
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <span className={styles.logo} aria-hidden><LukoLogo height={30} /></span>
        <div>
          <h2>لوکو؛ شهری که بچه‌ها در آن با بازی یاد می‌گیرند</h2>
          <p>
            این پنل آینه‌ی همان مسیر برای شماست: چقدر تمرین کرد، کجا قوی است، کجا کمک لازم دارد و حالش چطور است؛
            تا بدونِ سخت‌گیری، کنارش باشید.
          </p>
        </div>
      </section>

      <section className={form.card} aria-labelledby="rules-title">
        <h3 id="rules-title" className={form.cardTitle}>قوانین و حریم خصوصی</h3>
        <ul className={styles.rules}>
          {RULES.map((rule, i) => {
            const on = open === i;
            return (
              <li key={rule.title} data-open={on || undefined}>
                <button type="button" aria-expanded={on} onClick={() => setOpen(on ? null : i)}>
                  {rule.title}<HiOutlineChevronDown aria-hidden />
                </button>
                {on && <p>{rule.body}</p>}
              </li>
            );
          })}
        </ul>
      </section>

      <TrustSeals />

      <section className={form.card} aria-labelledby="contact-title">
        <h3 id="contact-title" className={form.cardTitle}>راه‌های ارتباط</h3>
        <ul className={styles.contact}>
          <li>
            <button type="button" onClick={() => env.open('support')}>
              <HiOutlineEnvelope aria-hidden /> تیکتِ پشتیبانی: پاسخِ مکتوب و ماندگار
            </button>
          </li>
          {/* اپِ کافه‌بازار پیوند به سایت ندارد (سایت اشتراک را با درگاهِ دیگر می‌فروشد؛ قانونِ پرداختِ بازار) */}
          {!BAZAAR_BUILD && (
            <li>
              <a href="https://my.luko.ir" target="_blank" rel="noopener">
                <HiOutlineGlobeAlt aria-hidden /> <span dir="ltr">my.luko.ir</span>
              </a>
            </li>
          )}
        </ul>
        <p className={styles.made}><HiOutlineHeart aria-hidden /> ساخته‌شده با عشق برای بچه‌های ایران</p>
      </section>
    </div>
  );
}
