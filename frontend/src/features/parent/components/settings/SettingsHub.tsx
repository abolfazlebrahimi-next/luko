import { useState } from 'react';
import type { ComponentType, SVGProps } from 'react';
import {
  HiOutlineArrowRightOnRectangle,
  HiOutlineBell,
  HiOutlineChatBubbleLeftRight,
  HiOutlineCheckBadge,
  HiOutlineChevronLeft,
  HiOutlineInformationCircle,
  HiOutlinePencilSquare,
  HiOutlineShieldCheck,
  HiOutlineUserPlus,
} from 'react-icons/hi2';
import { CrownIcon } from '@/components/ui/icons';
import { authApi } from '@/features/auth/api';
import { useAuth } from '@/features/auth/context';
import { useTicketList } from '../../useSettings';
import { Sheet } from '../shell/Sheet';
import { TrustSeals } from './TrustSeals';
import { childName, useSettingsEnv } from './SettingsContext';
import type { SettingsSection } from './SettingsContext';
import { fa } from '../health/moods';
import form from './form.module.css';
import styles from './SettingsHub.module.css';

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

interface Row {
  key: SettingsSection;
  icon: Icon;
  tone: string;
  title: string;
  note: string;
  badge?: string;
}

/** صفحه‌ی اصلیِ تنظیمات: والد، فرزندان، بخش‌ها و نمادِ اعتماد */
export function SettingsHub() {
  const env = useSettingsEnv();
  const tickets = useTicketList(undefined, !env.guest);
  const [editing, setEditing] = useState(false);

  const active = env.subscriptions?.filter((sub) => sub.status === 'active') ?? [];
  const unreadTickets = tickets.data?.unread ?? 0;
  const openTickets = (tickets.data?.counts.open ?? 0) + (tickets.data?.counts.answered ?? 0);
  const unread = env.notifications?.unread ?? 0;

  const rows: Row[] = [
    {
      key: 'billing', icon: CrownIcon, tone: 'sun', title: 'اشتراک و پرداخت‌ها',
      note: active.length
        ? `${fa(active.length)} فرزند با اشتراکِ فعال · صورت‌حساب‌ها`
        : 'همه روی پلنِ رایگان · پلن‌ها و صورت‌حساب‌ها',
    },
    {
      key: 'notifications', icon: HiOutlineBell, tone: 'teal', title: 'اعلان‌ها',
      note: unread ? `${fa(unread)} اعلانِ خوانده‌نشده` : 'همه‌ی اعلان‌ها و تنظیمِ آن‌ها',
      badge: unread ? fa(unread) : undefined,
    },
    {
      key: 'support', icon: HiOutlineChatBubbleLeftRight, tone: 'violet', title: 'پشتیبانی و تیکت‌ها',
      note: unreadTickets
        ? `${fa(unreadTickets)} پاسخِ تازه از پشتیبانی`
        : openTickets ? `${fa(openTickets)} تیکتِ در جریان` : 'سؤال‌های پرتکرار و تیکت',
      badge: unreadTickets ? fa(unreadTickets) : undefined,
    },
    {
      key: 'privacy', icon: HiOutlineShieldCheck, tone: 'green', title: 'حریم خصوصی و امنیت',
      note: 'رمز و شماره‌ی شما و فرزندان',
    },
    {
      key: 'about', icon: HiOutlineInformationCircle, tone: 'gray', title: 'درباره‌ی لوکو',
      note: 'قوانین، حریم خصوصی و نمادِ اعتماد',
    },
  ];

  return (
    <div className={styles.hub}>
      <section className={styles.parent} aria-label="حسابِ شما">
        <span className={styles.avatar} aria-hidden>{env.parentName.charAt(0) || 'و'}</span>
        <div className={styles.who}>
          <b>{env.parentName || 'والدِ لوکو'}</b>
          <span className={styles.phone}>
            <span dir="ltr">{env.parentPhone}</span>
            {env.phoneVerified && <em><HiOutlineCheckBadge aria-hidden /> تأییدشده</em>}
          </span>
        </div>
        <button type="button" className={styles.edit} onClick={() => (env.guest ? env.onNotice('در حالتِ نمایشی نام عوض نمی‌شود') : setEditing(true))}>
          <HiOutlinePencilSquare aria-hidden /> ویرایش
        </button>
        <ul className={styles.facts}>
          <li><b>{fa(env.childList.length)}</b><span>فرزند</span></li>
          <li><b>{fa(active.length)}</b><span>اشتراکِ فعال</span></li>
          <li><b>{fa(openTickets)}</b><span>تیکتِ در جریان</span></li>
        </ul>
      </section>

      <section className={styles.card} data-area="children" aria-labelledby="hub-children">
        <header className={styles.cardHead}>
          <h2 id="hub-children">فرزندان</h2>
          <button type="button" className={styles.link} onClick={env.onAddChild}>
            <HiOutlineUserPlus aria-hidden /> افزودن
          </button>
        </header>
        {env.childList.length === 0 ? (
          <p className={styles.empty}>هنوز فرزندی اضافه نکرده‌اید.</p>
        ) : (
          <ul className={styles.kids}>
            {env.childList.map((child) => {
              const sub = env.subscriptions?.find((item) => item.childId === child.id);
              const premium = sub?.status === 'active';
              return (
                <li key={child.id}>
                  <button type="button" className={styles.kid} onClick={() => env.open('child', child.id)}>
                    <span className={styles.kidAvatar} aria-hidden>{childName(child).charAt(0)}</span>
                    <span className={styles.kidText}>
                      <b>{childName(child)}{child.online && <i className={styles.online} aria-label="آنلاین" />}</b>
                      <small>پایه‌ی {fa(child.grade)}{child.school ? ` · ${child.school}` : ''}</small>
                    </span>
                    <span className={styles.plan} data-premium={premium || undefined}>
                      {premium ? <><CrownIcon size={12} strokeWidth={2.2} aria-hidden /> {sub?.lifetime ? 'همیشگی' : `${fa(sub?.daysLeft ?? 0)} روز`}</> : 'رایگان'}
                    </span>
                    <HiOutlineChevronLeft className={styles.chev} aria-hidden />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <nav className={styles.card} data-area="sections" aria-label="بخش‌های تنظیمات">
        <ul className={styles.rows}>
          {rows.map((row) => {
            const RowIcon = row.icon;
            return (
              <li key={row.key}>
                <button type="button" className={styles.row} onClick={() => env.open(row.key)}>
                  <span className={styles.rowIcon} data-tone={row.tone} aria-hidden><RowIcon /></span>
                  <span className={styles.rowText}><b>{row.title}</b><small>{row.note}</small></span>
                  {row.badge && <span className={styles.badge}>{row.badge}</span>}
                  <HiOutlineChevronLeft className={styles.chev} aria-hidden />
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className={styles.trust} data-area="trust">
        <TrustSeals />
        <button type="button" className={styles.logout} onClick={env.onLogout}>
          <HiOutlineArrowRightOnRectangle aria-hidden /> خروج از حساب
        </button>
      </div>

      {!env.guest && <NameSheet open={editing} onClose={() => setEditing(false)} />}
    </div>
  );
}

/** ویرایشِ نامِ والد — همان /auth/me */
function NameSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, setUser } = useAuth();
  const env = useSettingsEnv();
  const [first, setFirst] = useState(user?.firstName ?? '');
  const [last, setLast] = useState(user?.lastName ?? '');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!first.trim()) {
      env.onNotice('نام خالی نمی‌ماند.');
      return;
    }
    setBusy(true);
    try {
      setUser(await authApi.updateMe({ firstName: first.trim(), lastName: last.trim() }));
      env.onNotice('نامِ شما به‌روز شد');
      onClose();
    } catch {
      env.onNotice('ذخیره نشد؛ دوباره تلاش کنید.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} title="ویرایشِ نام" onClose={onClose}>
      <label className={form.field}>
        نام
        <input value={first} onChange={(e) => setFirst(e.target.value)} autoComplete="given-name" />
      </label>
      <label className={form.field}>
        نام خانوادگی
        <input value={last} onChange={(e) => setLast(e.target.value)} autoComplete="family-name" />
      </label>
      <button type="button" className={form.primary} disabled={busy} onClick={() => void save()}>
        {busy ? 'در حالِ ذخیره…' : 'ذخیره'}
      </button>
    </Sheet>
  );
}
