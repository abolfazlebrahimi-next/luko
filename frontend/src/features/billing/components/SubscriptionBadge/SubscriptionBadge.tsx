import { CrownIcon } from '@/components/ui/icons';
import { faNumber } from '../../format';
import type { ChildSubscription } from '../../types';
import styles from './SubscriptionBadge.module.css';

interface Props {
  sub?: ChildSubscription;
  /** نامِ کوچکِ همان فرزندی که پنل الان نشانش می‌دهد */
  childName: string;
  onClick: () => void;
}

/**
 * نشانِ اشتراکِ فرزندِ انتخاب‌شده در نوارِ بالای پنل — رایگان، چند روز مانده،
 * یا (۷ روز و کمتر) نارنجیِ «رو به پایان». ضربه → صفحه‌ی اشتراک.
 */
export function SubscriptionBadge({ sub, childName, onClick }: Props) {
  const active = sub?.status === 'active';
  const tone = !active ? 'free' : sub.expiringSoon ? 'warn' : 'active';
  const label = active ? (sub.lifetime ? 'همیشگی' : `${faNumber(sub.daysLeft)} روز`) : 'رایگان';
  const aria = active
    ? sub.lifetime
      ? `اشتراکِ همیشگیِ ${childName}، مشاهده`
      : `اشتراکِ ${sub.planTitle} ${childName}: ${faNumber(sub.daysLeft)} روز مانده، مشاهده و تمدید`
    : `${childName} روی پلنِ رایگان است، مشاهده‌ی پلن‌های اشتراک`;

  return (
    <button type="button" className={styles.badge} data-tone={tone} onClick={onClick} aria-label={aria}>
      <span className={styles.crown} aria-hidden>
        <CrownIcon size={15} strokeWidth={2} />
      </span>
      <span className={styles.label}>{label}</span>
      {tone === 'warn' && <span className={styles.pulse} aria-hidden />}
    </button>
  );
}
