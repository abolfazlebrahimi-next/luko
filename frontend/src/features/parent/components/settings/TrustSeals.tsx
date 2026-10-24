import { BAZAAR_BUILD } from '@/features/billing/bazaar';
import styles from './TrustSeals.module.css';

const ENAMAD_LINK = 'https://trustseal.enamad.ir/?id=8028112&Code=6qCdfbdgMb9dFb6ERmhx6w13ggY2hHhV';
const ENAMAD_IMAGE = 'https://trustseal.enamad.ir/logo.aspx?id=8028112&Code=6qCdfbdgMb9dFb6ERmhx6w13ggY2hHhV';

/**
 * دامنه‌ای که درگاهِ زیبالِ لوکو برایش ثبت و تأیید شده (gateway.zibal.ir/trustMe/<دامنه>؛ my.luko.ir «تاییدنشده»
 * است). روشِ HTMLِ خالصِ مستنداتِ زیبال: بی‌اسکریپتِ بیرونی.
 */
const ZIBAL_DOMAIN = 'panel.luko.ir';
const ZIBAL_LINK = `https://gateway.zibal.ir/trustMe/${ZIBAL_DOMAIN}`;
/** نسخه‌ی روشنِ نشان (۱.png)؛ ۲.png تیره است */
const ZIBAL_IMAGE = 'https://zibal.ir/trust/assets/1.png';

/**
 * نمادِ اعتمادِ الکترونیکی (اینماد) و نشانِ اعتمادِ زیبال کنارِ هم. اینماد نشانی و referrerِ صفحه را می‌سنجد؛
 * برای همین `referrerPolicy="origin"` روی همان پیوند و تصویر است (سربرگِ سایت same-origin است).
 * اپِ کافه‌بازار نشان نمی‌دهد: پرداختش با بازار است، نه زیبال، و پیوند به درگاه یا سایت در آن ممنوع است.
 */
export function TrustSeals() {
  if (BAZAAR_BUILD) return null;
  return (
    <div className={styles.card}>
      <div className={styles.seals}>
        <a className={styles.seal} referrerPolicy="origin" target="_blank" rel="noopener" href={ENAMAD_LINK}
          aria-label="نمادِ اعتمادِ الکترونیکیِ لوکو">
          <img referrerPolicy="origin" src={ENAMAD_IMAGE} alt="" style={{ cursor: 'pointer' }}
            {...{ code: '6qCdfbdgMb9dFb6ERmhx6w13ggY2hHhV' }} />
        </a>
        <a className={styles.seal} data-kind="zibal" target="_blank" rel="noopener" href={ZIBAL_LINK}
          aria-label="نشانِ اعتمادِ زیبال: پرداخت‌یارِ لوکو">
          <img src={ZIBAL_IMAGE} alt="" width={109} height={152} loading="lazy" decoding="async" />
        </a>
      </div>
      <div className={styles.text}>
        <b>نمادهای اعتماد</b>
        <p>
          لوکو نمادِ اعتمادِ الکترونیکی دارد و پرداخت‌ها با درگاهِ امنِ زیبال (شاپرک) انجام می‌شود؛ اطلاعاتِ کارت به
          لوکو نمی‌رسد.
        </p>
      </div>
    </div>
  );
}
