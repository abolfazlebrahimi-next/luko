import {
  HiOutlineArrowRightOnRectangle,
  HiOutlineChatBubbleLeftRight,
  HiOutlinePlus,
} from 'react-icons/hi2';
import { CrownIcon } from '@/components/ui/icons';
import { LukoLogo } from '@/components/ui/LukoLogo/LukoLogo';
import { NAV_ITEMS } from './nav';
import type { PanelPage } from './nav';
import type { ShellProps } from './ParentShell';
import styles from './SideNav.module.css';

const GRADES = ['', 'پایه اول', 'پایه دوم', 'پایه سوم', 'پایه چهارم', 'پایه پنجم', 'پایه ششم'];
const fa = (value: number) => value.toLocaleString('fa-IR');

type Props = ShellProps & { active: PanelPage };

/** منوی کناریِ راست در لپ‌تاپ و نمایشگرهای بزرگ: والد، فرزندان، صفحه‌ها و اشتراک */
export function SideNav({
  active, onNavigate, parentName, parentPhone, childList, activeChildId, onChildChange, onAddChild,
  subscription, childName, onSubscription, onSupport, onLogout,
}: Props) {
  const premium = subscription?.status === 'active';
  return (
    <aside className={styles.side} aria-label="منوی پنل والدین">
      <div className={styles.brand}>
        <LukoLogo height={30} className={styles.logo} />
        <span className={styles.brandText}><b className={styles.srOnly}>لوکو</b><small>پنل والدین</small></span>
      </div>

      <button type="button" className={styles.parent} onClick={() => onNavigate('settings')}>
        <span className={styles.avatar} aria-hidden>{parentName.charAt(0) || 'و'}</span>
        <span className={styles.parentText}>
          <b>{parentName || 'والدِ عزیز'}</b>
          {parentPhone && <small dir="ltr">{parentPhone}</small>}
        </span>
      </button>

      {childList.length > 0 && (
        <div className={styles.group}>
          <p className={styles.groupTitle}>فرزندان</p>
          <div role="tablist" aria-label="انتخابِ فرزند" className={styles.kids}>
            {childList.map((child) => {
              const name = `${child.firstName} ${child.lastName}`.trim() || 'بدون نام';
              const on = child.id === activeChildId;
              return (
                <button key={child.id} type="button" role="tab" aria-selected={on} className={styles.kid}
                  data-active={on || undefined} onClick={() => onChildChange(child.id)}>
                  <span className={styles.kidAvatar} aria-hidden>{name.charAt(0)}</span>
                  <span className={styles.kidText}>
                    <b>{name}</b>
                    <small>{GRADES[child.grade] ?? `پایه ${fa(child.grade)}`}</small>
                  </span>
                </button>
              );
            })}
          </div>
          <button type="button" className={styles.addKid} onClick={onAddChild}>
            <HiOutlinePlus aria-hidden /> افزودنِ فرزند
          </button>
        </div>
      )}

      <nav className={styles.nav} aria-label="صفحه‌های پنل">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const on = item.key === active;
          return (
            <button key={item.key} type="button" className={styles.link} data-active={on || undefined}
              aria-current={on ? 'page' : undefined} onClick={() => onNavigate(item.key)}>
              <Icon aria-hidden />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className={styles.spacer} />

      {activeChildId && (premium ? (
        <button type="button" className={styles.planActive} onClick={onSubscription}>
          <CrownIcon size={18} strokeWidth={2} />
          <span>
            <b>اشتراکِ {childName} فعال است</b>
            <small>{subscription?.lifetime ? 'همیشگی' : `${fa(subscription?.daysLeft ?? 0)} روز مانده`}</small>
          </span>
        </button>
      ) : (
        <div className={styles.upsell}>
          <span className={styles.upsellIcon} aria-hidden><CrownIcon size={20} strokeWidth={2} /></span>
          <b>همه‌ی درس‌های {childName} را باز کنید</b>
          <p>با اشتراکِ لوکو گزارشِ همه‌ی درس‌ها و پیشنهادهای شخصیِ هر هفته را می‌بینید.</p>
          <button type="button" onClick={onSubscription}>دیدنِ پلن‌ها</button>
        </div>
      ))}

      <div className={styles.footer}>
        <button type="button" onClick={onSupport}><HiOutlineChatBubbleLeftRight aria-hidden /> پشتیبانی</button>
        <button type="button" onClick={onLogout}><HiOutlineArrowRightOnRectangle aria-hidden /> خروج</button>
      </div>
    </aside>
  );
}
