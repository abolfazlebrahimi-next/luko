import { useState } from 'react';
import {
  HiOutlineAcademicCap,
  HiOutlineCalendarDays,
  HiOutlineChartBar,
  HiOutlineComputerDesktop,
  HiOutlineDevicePhoneMobile,
  HiOutlineFire,
  HiOutlinePaintBrush,
  HiOutlinePencilSquare,
  HiOutlinePuzzlePiece,
  HiOutlineSparkles,
  HiOutlineStar,
  HiOutlineTrash,
  HiOutlineTrophy,
} from 'react-icons/hi2';
import { CoinIcon, CrownIcon } from '@/components/ui/icons';
import type { ChildProfile } from '../../settingsTypes';
import { apiError } from '../../settingsApi';
import { useChildProfile, useUpdateChild } from '../../useSettings';
import { ChildAccountCard } from '../children/ChildAccountCard';
import { fa } from '../health/moods';
import { Sheet } from '../shell/Sheet';
import { guestProfile } from './guestSettings';
import { useSettingsEnv } from './SettingsContext';
import form from './form.module.css';
import styles from './ChildProfilePage.module.css';

interface Props {
  childId: string;
}

/** مشخصاتِ کاملِ یک فرزند: هویت، حضور، آمار، اشتراک، ورود و امنیت */
export function ChildProfilePage({ childId }: Props) {
  const env = useSettingsEnv();
  const child = env.childList.find((item) => item.id === childId);
  const query = useChildProfile(childId, !env.guest && Boolean(child));
  const profile = env.guest ? (child ? guestProfile(child) : undefined) : query.data;
  const [editing, setEditing] = useState(false);

  if (!child) return <p className={styles.empty}>این فرزند در حسابِ شما نیست.</p>;
  if (!profile) {
    return query.isError
      ? <p className={styles.empty}>مشخصات بارگذاری نشد. <button type="button" onClick={() => void query.refetch()}>تلاشِ دوباره</button></p>
      : <div className={styles.skeleton} aria-hidden><i /><i /><i /></div>;
  }

  const name = `${profile.firstName} ${profile.lastName}`.trim() || 'بدونِ نام';
  const stats = [
    { icon: CoinIcon, label: 'سکه', value: profile.stats.coins },
    { icon: HiOutlineStar, label: 'امتیاز', value: profile.stats.points },
    { icon: HiOutlinePuzzlePiece, label: 'بازیِ کامل', value: profile.stats.gamesCompleted },
    { icon: HiOutlineTrophy, label: 'مدال', value: profile.stats.medals },
    { icon: HiOutlineFire, label: 'روزِ پیاپی', value: profile.stats.streak },
    { icon: HiOutlineSparkles, label: 'گنج', value: profile.stats.treasures },
    { icon: HiOutlinePaintBrush, label: 'نقاشی', value: profile.stats.paintings },
    { icon: HiOutlineChartBar, label: 'گفتنِ حال', value: profile.stats.checkins },
  ];
  const details: [string, React.ReactNode][] = [
    ['نام', profile.firstName || 'ثبت نشده'],
    ['نام خانوادگی', profile.lastName || 'ثبت نشده'],
    ['پایه', profile.gradeLabel],
    ['مدرسه', profile.school || 'ثبت نشده'],
    ['شماره‌ی ورود', <span key="p" dir="ltr">{profile.phone}</span>],
    ['نسبتِ شما', profile.relation || 'والد'],
    ['عضوِ لوکو از', profile.joinedFa],
    ['وصل به حسابِ شما از', profile.linkedFa],
  ];
  const PlatformIcon = profile.platform === 'android' ? HiOutlineDevicePhoneMobile : HiOutlineComputerDesktop;

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <span className={styles.avatar} aria-hidden>{name.charAt(0)}</span>
        <div className={styles.heroText}>
          <h2>{name}</h2>
          <p>{profile.gradeLabel}{profile.school ? ` · ${profile.school}` : ''}</p>
          <span className={styles.presence} data-online={profile.online || undefined}>
            <i aria-hidden />
            {profile.online ? 'همین حالا در لوکو' : profile.lastSeenFa ? `آخرین حضور: ${profile.lastSeenFa}` : 'هنوز وارد نشده'}
            {profile.platform && <><PlatformIcon aria-hidden /> {profile.platform === 'android' ? 'اپِ اندروید' : 'سایت'}</>}
          </span>
        </div>
        <span className={styles.plan} data-premium={profile.subscription.active || undefined}>
          <CrownIcon size={14} strokeWidth={2.2} aria-hidden />
          {profile.subscription.lifetime ? 'اشتراکِ همیشگی'
            : profile.subscription.active ? `${fa(profile.subscription.daysLeft)} روز اشتراک` : 'پلنِ رایگان'}
        </span>
      </section>

      <section className={form.card} data-area="details" aria-labelledby="child-details">
        <header className={styles.head}>
          <h3 id="child-details" className={form.cardTitle}>مشخصات</h3>
          <button type="button" className={styles.edit}
            onClick={() => (env.guest ? env.onNotice('در حالتِ نمایشی ویرایش نمی‌شود') : setEditing(true))}>
            <HiOutlinePencilSquare aria-hidden /> ویرایش
          </button>
        </header>
        <dl className={styles.details}>
          {details.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
          ))}
        </dl>
        <p className={styles.note}>
          <HiOutlineAcademicCap aria-hidden />
          پایه از این‌جا عوض نمی‌شود چون مسیرِ بازی‌ها به آن بسته است؛ اگر لازم است، از پشتیبانی بخواهید.
        </p>
      </section>

      <section className={form.card} data-area="stats" aria-labelledby="child-stats">
        <h3 id="child-stats" className={form.cardTitle}>{name} در لوکو</h3>
        <p className={form.cardNote}>
          <HiOutlineCalendarDays aria-hidden className={styles.inlineIcon} /> {fa(profile.joinedDays)} روز است که عضوِ لوکو است
        </p>
        <ul className={styles.stats}>
          {stats.map(({ icon: Icon, label, value }) => (
            <li key={label}>
              <Icon aria-hidden />
              <b>{fa(value)}</b>
              <span>{label}</span>
            </li>
          ))}
        </ul>
        {!profile.subscription.active && (
          <button type="button" className={styles.upsell} onClick={() => env.open('billing', undefined, { child: childId })}>
            <CrownIcon size={18} strokeWidth={2} aria-hidden />
            <span><b>گزارشِ همه‌ی درس‌ها و حالِ روزانه‌ی {profile.firstName || name}</b><small>با اشتراک باز می‌شود</small></span>
          </button>
        )}
        {profile.subscription.active && (
          <p className={styles.active}>
            <CrownIcon size={16} strokeWidth={2} aria-hidden />
            اشتراکِ {profile.subscription.planTitle} تا {profile.subscription.endsFa} فعال است.
            <button type="button" onClick={() => env.open('billing', undefined, { child: childId })}>مدیریت</button>
          </p>
        )}
      </section>

      <section className={form.card} data-area="security" aria-labelledby="child-security">
        <h3 id="child-security" className={form.cardTitle}>ورود و امنیتِ حساب</h3>
        <p className={form.cardNote}>رمزِ ورودِ {profile.firstName || name} را ببینید یا عوض کنید، یا شماره‌اش را تغییر دهید.</p>
        {env.guest
          ? <p className={styles.empty}>در حالتِ نمایشی رمز و شماره نشان داده نمی‌شود.</p>
          : <ChildAccountCard child={child} onDone={env.onNotice} />}
      </section>

      <section className={styles.danger} data-area="danger">
        <div>
          <b>قطعِ دسترسی</b>
          <p>گزارش‌های {profile.firstName || name} دیگر برای شما نمی‌آید؛ حساب و پیشرفتِ خودش می‌ماند.</p>
        </div>
        <button type="button" className={form.danger} onClick={() => env.onRemoveChild(child)}>
          <HiOutlineTrash aria-hidden /> قطعِ دسترسی
        </button>
      </section>

      {!env.guest && (
        <EditChildSheet open={editing} profile={profile} onClose={() => setEditing(false)} />
      )}
    </div>
  );
}

function EditChildSheet({ open, profile, onClose }: { open: boolean; profile: ChildProfile; onClose: () => void }) {
  const env = useSettingsEnv();
  const update = useUpdateChild(profile.id);
  const [first, setFirst] = useState(profile.firstName);
  const [last, setLast] = useState(profile.lastName);
  const [school, setSchool] = useState(profile.school);

  const save = () => {
    update.mutate(
      { firstName: first.trim(), lastName: last.trim(), school: school.trim() },
      { onSuccess: () => { env.onNotice('مشخصات به‌روز شد'); onClose(); } },
    );
  };

  return (
    <Sheet open={open} title="ویرایشِ مشخصات" onClose={onClose}>
      {update.isError && <p className={form.error} role="alert">{apiError(update.error, 'ذخیره نشد؛ دوباره تلاش کنید.')}</p>}
      <label className={form.field}>نام<input value={first} onChange={(e) => setFirst(e.target.value)} /></label>
      <label className={form.field}>نام خانوادگی<input value={last} onChange={(e) => setLast(e.target.value)} /></label>
      <label className={form.field}>مدرسه<input value={school} onChange={(e) => setSchool(e.target.value)} placeholder="اختیاری" /></label>
      <button type="button" className={form.primary} disabled={update.isPending || !first.trim()} onClick={save}>
        {update.isPending ? 'در حالِ ذخیره…' : 'ذخیره'}
      </button>
    </Sheet>
  );
}
