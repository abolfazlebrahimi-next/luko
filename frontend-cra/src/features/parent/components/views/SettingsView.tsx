import {
  HiOutlineArrowLeftOnRectangle,
  HiOutlineBell,
  HiOutlineChatBubbleLeftRight,
  HiOutlineChevronLeft,
  HiOutlineInformationCircle,
  HiOutlineShieldCheck,
  HiOutlineSignal,
  HiOutlineTrash,
  HiOutlineUserPlus,
} from 'react-icons/hi2';
import type { Child, ParentPreferences } from '../../types';
import { Card, SectionTitle } from '../shell/Card';
import styles from './SettingsView.module.css';
import { ReferralCard } from './ReferralCard';
import { isGuestParentPreview } from '../../demoMode';

interface Props {
  parentName: string;
  parentPhone: string;
  childList: Child[];
  preferences?: ParentPreferences;
  onToggle: (key: keyof ParentPreferences, value: boolean) => void;
  onAddChild: () => void;
  onRemoveChild: (child: Child) => void;
  onSupport: () => void;
  onPrivacy: () => void;
  onAbout: () => void;
  onLogout: () => void;
}

const GRADES = ['', 'پایه اول', 'پایه دوم', 'پایه سوم', 'پایه چهارم', 'پایه پنجم', 'پایه ششم'];

/** تنظیمات — حساب، فرزندان، سوییچ‌ها و پشتیبانی */
export function SettingsView({
  parentName,
  parentPhone,
  childList,
  preferences,
  onToggle,
  onAddChild,
  onRemoveChild,
  onSupport,
  onPrivacy,
  onAbout,
  onLogout,
}: Props) {
  return (
    <>
      <Card>
        <div className={styles.profile}>
          <span className={styles.avatar} aria-hidden>
            {parentName.charAt(0) || 'و'}
          </span>
          <div>
            <b>{parentName || 'والدِ لوکو'}</b>
            <small dir="ltr">{parentPhone}</small>
          </div>
        </div>
      </Card>

      {!isGuestParentPreview() && <ReferralCard children={childList} />}

      <SectionTitle>فرزندان</SectionTitle>
      <Card flush>
        {childList.map((child) => {
          const name = `${child.firstName} ${child.lastName}`.trim() || 'بدون نام';
          return (
            <div key={child.id} className={styles.row}>
              <span className={styles.childAvatar} aria-hidden>
                {name.charAt(0)}
              </span>
              <span className={styles.rowText}>
                {name}
                <small>
                  {GRADES[child.grade] ?? `پایه ${child.grade}`}
                  {child.school ? ` · ${child.school}` : ''}
                </small>
              </span>
              <button
                type="button"
                className={styles.rowAction}
                onClick={() => onRemoveChild(child)}
                aria-label={`حذف دسترسی به ${name}`}
              >
                <HiOutlineTrash aria-hidden />
              </button>
            </div>
          );
        })}

        <button type="button" className={styles.rowButton} onClick={onAddChild}>
          <span className={styles.rowIcon}>
            <HiOutlineUserPlus aria-hidden />
          </span>
          افزودن فرزند
          <HiOutlineChevronLeft className={styles.arrow} aria-hidden />
        </button>
      </Card>

      <SectionTitle>اعلان‌ها</SectionTitle>
      <Card flush>
        <div className={styles.row}>
          <span className={styles.rowIcon}>
            <HiOutlineBell aria-hidden />
          </span>
          <span className={styles.rowText}>
            گزارش هفتگی
            <small>هر هفته خلاصهٔ پیشرفت فرزندتان</small>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={preferences?.weeklyReport ?? true}
            aria-label="اعلان گزارش هفتگی"
            className={preferences?.weeklyReport ? styles.switchOn : styles.switch}
            onClick={() => onToggle('weeklyReport', !(preferences?.weeklyReport ?? true))}
          />
        </div>

        <div className={styles.row}>
          <span className={styles.rowIcon}>
            <HiOutlineSignal aria-hidden />
          </span>
          <span className={styles.rowText}>
            هشدارهای فعالیت
            <small>بازی‌های تازه، ثبت حال و روزهای بی‌فعالیتی</small>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={preferences?.activityAlerts ?? true}
            aria-label="هشدارهای فعالیت"
            className={preferences?.activityAlerts ? styles.switchOn : styles.switch}
            onClick={() => onToggle('activityAlerts', !(preferences?.activityAlerts ?? true))}
          />
        </div>
      </Card>

      <SectionTitle>حساب</SectionTitle>
      <Card flush>
        <button type="button" className={styles.rowButton} onClick={onSupport}>
          <span className={styles.rowIcon}>
            <HiOutlineChatBubbleLeftRight aria-hidden />
          </span>
          پشتیبانی و گفتگو
          <HiOutlineChevronLeft className={styles.arrow} aria-hidden />
        </button>

        <button type="button" className={styles.rowButton} onClick={onPrivacy}>
          <span className={styles.rowIcon}>
            <HiOutlineShieldCheck aria-hidden />
          </span>
          حریم خصوصی و امنیت
          <HiOutlineChevronLeft className={styles.arrow} aria-hidden />
        </button>

        <button type="button" className={styles.rowButton} onClick={onAbout}>
          <span className={styles.rowIcon}>
            <HiOutlineInformationCircle aria-hidden />
          </span>
          دربارهٔ لوکو
          <HiOutlineChevronLeft className={styles.arrow} aria-hidden />
        </button>

        <button type="button" className={styles.rowDanger} onClick={onLogout}>
          <span className={styles.rowIconDanger}>
            <HiOutlineArrowLeftOnRectangle aria-hidden />
          </span>
          خروج از حساب
        </button>
      </Card>

      <p className={styles.version}>لوکو · پنل والدین — ساخته‌شده برای خانواده‌ها</p>
    </>
  );
}
