import { useEffect, useMemo, useState } from 'react';
import {
  HiOutlineBell,
  HiOutlineCheckBadge,
  HiOutlineExclamationTriangle,
  HiOutlineFaceSmile,
  HiOutlineMoon,
  HiOutlinePaperAirplane,
  HiOutlinePuzzlePiece,
  HiOutlineTrophy,
} from 'react-icons/hi2';
import { useAuth } from 'features/auth/context';
import { BrandMark } from 'components/ui/icons';
import { buildAnalysis } from 'features/parent/analysis';
import type { Child, ParentPreferences, Suggestion } from 'features/parent/types';
import {
  useAddChild,
  useAssignments,
  useChildren,
  useCreateTicket,
  useMarkNotificationsRead,
  useNotifications,
  usePreferences,
  useRemoveChild,
  useReport,
  useSetAssignment,
  useSetPreferences,
  useSuggestions,
} from 'features/parent/useParent';
import { BottomNav } from 'features/parent/components/shell/BottomNav';
import type { PanelTab } from 'features/parent/components/shell/BottomNav';
import { ChildSwitch } from 'features/parent/components/shell/ChildSwitch';
import { Sheet } from 'features/parent/components/shell/Sheet';
import { Toast } from 'features/parent/components/shell/Toast';
import { DashboardView } from 'features/parent/components/views/DashboardView';
import { ReportsView } from 'features/parent/components/views/ReportsView';
import { DailyView } from 'features/parent/components/views/DailyView';
import { HealthView } from 'features/parent/components/views/HealthView';
import { SettingsView } from 'features/parent/components/views/SettingsView';
import styles from './ParentPanel.module.css';

type SheetKind = 'notifications' | 'support' | 'addChild' | 'removeChild' | 'logout' | 'privacy' | 'about';

const NOTIF_ICON = {
  weekly: HiOutlineTrophy,
  games: HiOutlinePuzzlePiece,
  mood: HiOutlineFaceSmile,
  idle: HiOutlineMoon,
  assignment: HiOutlineCheckBadge,
};

/** اسکلتِ بارگذاری — شکلِ نهایی را نگه می‌دارد تا صفحه نپرد */
function Skeleton() {
  return (
    <div className={styles.skeleton} aria-hidden>
      <div className={styles.skelSeg} />
      <div className={styles.skelBanner} />
      <div className={styles.skelCard} />
      <div className={styles.skelGrid}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={styles.skelTile} />
        ))}
      </div>
    </div>
  );
}

export default function ParentPanel() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<PanelTab>('dashboard');
  const [childId, setChildId] = useState<string>();
  const [sheet, setSheet] = useState<SheetKind | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [pendingChild, setPendingChild] = useState<Child | null>(null);
  const [form, setForm] = useState({ phone: '', firstName: '', grade: '1', school: '', password: '' });
  const [message, setMessage] = useState('');

  const children = useChildren();
  const notifications = useNotifications();
  const preferences = usePreferences();
  const report = useReport(childId);
  const assignments = useAssignments(childId);
  const suggestions = useSuggestions(childId);

  const setAssignment = useSetAssignment(childId);
  const setPreferences = useSetPreferences();
  const addChild = useAddChild();
  const removeChild = useRemoveChild();
  const markRead = useMarkNotificationsRead();
  const createTicket = useCreateTicket();

  // اولین فرزند به‌صورت پیش‌فرض انتخاب می‌شود
  useEffect(() => {
    if (!childId && children.data?.length) setChildId(children.data[0].id);
  }, [children.data, childId]);

  const activeChild = children.data?.find((child) => child.id === childId);
  const childName = activeChild
    ? `${activeChild.firstName} ${activeChild.lastName}`.trim() || 'فرزند شما'
    : 'فرزند شما';
  // در جمله‌های وسطِ متن، نامِ کوچک طبیعی‌تر است تا نام و نام‌خانوادگیِ کامل
  const shortName = activeChild?.firstName?.trim() || childName;

  const analysis = useMemo(
    () => (report.data ? (report.data.analysis ?? buildAnalysis(report.data, shortName)) : null),
    [report.data, shortName],
  );

  const parentName = `${user?.firstName ?? ''} ${user?.lastName ?? ''}`.trim();
  const unread = notifications.data?.unread ?? 0;

  const openNotifications = () => {
    setSheet('notifications');
    if (unread > 0) markRead.mutate();
  };

  const pickGame = (suggestion: Suggestion, date: string) => {
    setAssignment.mutate(
      { gameSlug: suggestion.slug, date },
      {
        onSuccess: () => setToast(`بازی «${suggestion.title}» برای ${shortName} ثبت شد`),
        onError: () => setToast('ثبت بازی روز انجام نشد؛ دوباره تلاش کنید.'),
      },
    );
  };

  const togglePreference = (key: keyof ParentPreferences, value: boolean) => {
    setPreferences.mutate(
      { [key]: value },
      {
        onSuccess: () =>
          setToast(
            key === 'weeklyReport'
              ? value
                ? 'اعلان گزارش هفتگی روشن شد'
                : 'اعلان گزارش هفتگی خاموش شد'
              : value
                ? 'هشدارهای فعالیت روشن شد'
                : 'هشدارهای فعالیت خاموش شد',
          ),
      },
    );
  };

  const submitChild = () => {
    if (!/^09\d{9}$/.test(form.phone.trim())) {
      setToast('شمارهٔ موبایل باید ۱۱ رقم و با ۰۹ شروع شود.');
      return;
    }
    if (form.password.length < 6) {
      setToast('رمز فرزند باید دست‌کم ۶ نویسه باشد.');
      return;
    }
    addChild.mutate(
      {
        phone: form.phone.trim(),
        password: form.password,
        firstName: form.firstName.trim() || undefined,
        grade: Number(form.grade),
        school: form.school.trim() || undefined,
      },
      {
        onSuccess: (child) => {
          setSheet(null);
          setForm({ phone: '', firstName: '', grade: '1', school: '', password: '' });
          setChildId(child.id);
          setToast('فرزند به حساب شما اضافه شد');
        },
        onError: (error: unknown) => {
          const detail =
            (error as { response?: { data?: { error?: { message?: string } } } })?.response?.data
              ?.error?.message ?? 'افزودن فرزند انجام نشد.';
          setToast(detail);
        },
      },
    );
  };

  const confirmRemove = () => {
    if (!pendingChild) return;
    removeChild.mutate(pendingChild.id, {
      onSuccess: () => {
        setSheet(null);
        if (pendingChild.id === childId) setChildId(undefined);
        setPendingChild(null);
        setToast('دسترسی شما به این فرزند قطع شد');
      },
    });
  };

  const submitTicket = () => {
    const body = message.trim();
    if (body.length < 5) {
      setToast('پیام خیلی کوتاه است.');
      return;
    }
    createTicket.mutate(
      { subject: 'پرسش از پنل والدین', body },
      {
        onSuccess: () => {
          setSheet(null);
          setMessage('');
          setToast('پیام شما برای پشتیبانی ارسال شد');
        },
        onError: () => setToast('ارسال پیام انجام نشد؛ دوباره تلاش کنید.'),
      },
    );
  };

  const showSwitcher = tab !== 'settings' && (children.data?.length ?? 0) > 1;

  return (
    <div className={styles.app}>
      <header className={styles.bar}>
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden>
            <BrandMark size={22} />
          </span>
          <span className={styles.brandText}>
            <b>لوکو</b>
            <small>پنل والدین</small>
          </span>
        </div>

        <div className={styles.barActions}>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={openNotifications}
            aria-label={unread ? `اعلان‌ها، ${unread} خوانده‌نشده` : 'اعلان‌ها'}
          >
            <HiOutlineBell aria-hidden />
            {unread > 0 && <span className={styles.dot} aria-hidden />}
          </button>

          <div className={styles.userChip}>
            <span className={styles.userText}>
              <b>{parentName || 'والد'}</b>
              <small dir="ltr">{user?.phone}</small>
            </span>
            <span className={styles.userAvatar} aria-hidden>
              {parentName.charAt(0) || 'و'}
            </span>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <div className={styles.view} key={tab}>
          {showSwitcher && (
            <ChildSwitch
              items={children.data ?? []}
              activeId={childId}
              onChange={(id) => setChildId(id)}
            />
          )}

          {children.isLoading && <Skeleton />}

          {!children.isLoading && (children.data?.length ?? 0) === 0 && tab !== 'settings' && (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>هنوز فرزندی اضافه نکرده‌اید</p>
              <p className={styles.emptyText}>
                با شمارهٔ موبایلِ حساب فرزندتان او را اضافه کنید تا گزارش‌ها ساخته شوند.
              </p>
              <button type="button" className={styles.emptyBtn} onClick={() => setSheet('addChild')}>
                افزودن فرزند
              </button>
            </div>
          )}

          {tab === 'settings' && (
            <SettingsView
              parentName={parentName}
              parentPhone={user?.phone ?? ''}
              childList={children.data ?? []}
              preferences={preferences.data}
              onToggle={togglePreference}
              onAddChild={() => setSheet('addChild')}
              onRemoveChild={(child) => {
                setPendingChild(child);
                setSheet('removeChild');
              }}
              onSupport={() => setSheet('support')}
              onPrivacy={() => setSheet('privacy')}
              onAbout={() => setSheet('about')}
              onLogout={() => setSheet('logout')}
            />
          )}

          {tab !== 'settings' && childId && (
            <>
              {report.isLoading && <Skeleton />}

              {report.isError && (
                <div className={styles.emptyState}>
                  <p className={styles.emptyTitle}>گزارش بارگذاری نشد</p>
                  <p className={styles.emptyText}>اتصال را بررسی کنید و دوباره تلاش کنید.</p>
                  <button
                    type="button"
                    className={styles.emptyBtn}
                    onClick={() => report.refetch()}
                  >
                    تلاش دوباره
                  </button>
                </div>
              )}

              {report.data && analysis && tab === 'dashboard' && (
                <DashboardView
                  report={report.data}
                  analysis={analysis}
                  childName={shortName}
                  onGoDaily={() => setTab('daily')}
                />
              )}

              {report.data && tab === 'reports' && <ReportsView report={report.data} />}

              {tab === 'daily' && (
                <DailyView
                  childName={shortName}
                  suggestions={suggestions.data?.suggestions ?? []}
                  currentSlug={suggestions.data?.currentSlug ?? null}
                  assignments={assignments.data ?? []}
                  saving={setAssignment.isPending}
                  onPick={pickGame}
                />
              )}

              {report.data && tab === 'health' && (
                <HealthView report={report.data} childName={shortName} />
              )}
            </>
          )}
        </div>
      </main>

      <BottomNav tab={tab} onChange={setTab} />

      <Sheet
        open={sheet === 'notifications'}
        title="اعلان‌ها"
        onClose={() => setSheet(null)}
      >
        {(notifications.data?.items.length ?? 0) === 0 ? (
          <p className={styles.sheetText}>هنوز اعلانی ندارید.</p>
        ) : (
          notifications.data?.items.map((item) => {
            const Icon = NOTIF_ICON[item.kind] ?? HiOutlineBell;
            return (
              <div key={item.id} className={styles.notifRow}>
                <span className={styles.notifIcon} aria-hidden>
                  <Icon />
                </span>
                <div>
                  <b>{item.title}</b>
                  <small>
                    {item.body} · {item.at}
                  </small>
                </div>
              </div>
            );
          })
        )}
      </Sheet>

      <Sheet open={sheet === 'support'} title="گفتگو با پشتیبانی" onClose={() => setSheet(null)}>
        <p className={styles.sheetText}>
          هر سؤالی دربارهٔ گزارش‌ها یا حسابِ فرزندتان دارید همین‌جا بنویسید؛ تیم لوکو پاسخ می‌دهد.
        </p>
        <textarea
          className={styles.textarea}
          placeholder="پیام خود را بنویسید…"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
        />
        <button
          type="button"
          className={styles.btnPrimary}
          disabled={createTicket.isPending}
          onClick={submitTicket}
        >
          <HiOutlinePaperAirplane aria-hidden />
          {createTicket.isPending ? 'در حال ارسال…' : 'ارسال پیام'}
        </button>
      </Sheet>

      <Sheet open={sheet === 'addChild'} title="افزودن فرزند" onClose={() => setSheet(null)}>
        <p className={styles.sheetText}>
          شمارهٔ موبایلی که فرزندتان با آن وارد لوکو می‌شود را بنویسید.
        </p>
        <label className={styles.field}>
          شمارهٔ موبایل
          <input
            dir="ltr"
            inputMode="numeric"
            placeholder="09xxxxxxxxx"
            value={form.phone}
            onChange={(event) => setForm({ ...form, phone: event.target.value })}
          />
        </label>
        <label className={styles.field}>
          رمز ورود فرزند (حداقل ۶ نویسه)
          <input type="password" autoComplete="new-password" value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })} />
        </label>
        <label className={styles.field}>
          نام (اختیاری)
          <input
            value={form.firstName}
            onChange={(event) => setForm({ ...form, firstName: event.target.value })}
          />
        </label>
        <label className={styles.field}>
          پایهٔ تحصیلی
          <select
            value={form.grade}
            onChange={(event) => setForm({ ...form, grade: event.target.value })}
          >
            {[1, 2, 3, 4, 5, 6].map((grade) => (
              <option key={grade} value={grade}>
                پایه {grade.toLocaleString('fa-IR')}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          مدرسه (اختیاری)
          <input
            value={form.school}
            onChange={(event) => setForm({ ...form, school: event.target.value })}
          />
        </label>
        <button
          type="button"
          className={styles.btnPrimary}
          disabled={addChild.isPending}
          onClick={submitChild}
        >
          {addChild.isPending ? 'در حال افزودن…' : 'افزودن فرزند'}
        </button>
      </Sheet>

      <Sheet open={sheet === 'removeChild'} title="حذف دسترسی" onClose={() => setSheet(null)}>
        <p className={styles.sheetText}>
          دسترسی شما به گزارش‌های{' '}
          <b>
            {pendingChild
              ? `${pendingChild.firstName} ${pendingChild.lastName}`.trim() || 'این فرزند'
              : ''}
          </b>{' '}
          قطع می‌شود. حساب و پیشرفتِ خودِ فرزندتان دست‌نخورده می‌ماند.
        </p>
        <div className={styles.btnRow}>
          <button
            type="button"
            className={styles.btnDanger}
            disabled={removeChild.isPending}
            onClick={confirmRemove}
          >
            <HiOutlineExclamationTriangle aria-hidden />
            حذف دسترسی
          </button>
          <button type="button" className={styles.btnGhost} onClick={() => setSheet(null)}>
            انصراف
          </button>
        </div>
      </Sheet>

      <Sheet open={sheet === 'logout'} title="خروج از حساب" onClose={() => setSheet(null)}>
        <p className={styles.sheetText}>برای ادامهٔ کار باید دوباره وارد شوید. مطمئن هستید؟</p>
        <div className={styles.btnRow}>
          <button type="button" className={styles.btnDanger} onClick={logout}>
            خروج
          </button>
          <button type="button" className={styles.btnGhost} onClick={() => setSheet(null)}>
            انصراف
          </button>
        </div>
      </Sheet>

      <Sheet open={sheet === 'privacy'} title="حریم خصوصی و امنیت" onClose={() => setSheet(null)}>
        <p className={styles.sheetText}>
          گزارش‌های این پنل فقط از بازی‌های ثبت‌شده ساخته می‌شوند. نوشته‌های «صندوقچهٔ رازها»
          رمزنگاری‌شده‌اند و برای هیچ‌کس — از جمله شما — قابل دیدن نیستند. دسترسی هر والد فقط به
          فرزندانِ متصل به حساب خودش است.
        </p>
      </Sheet>

      <Sheet open={sheet === 'about'} title="دربارهٔ لوکو" onClose={() => setSheet(null)}>
        <p className={styles.sheetText}>
          لوکو شهری است که بچه‌ها در آن با بازی یاد می‌گیرند. این پنل، آینهٔ همان مسیر برای شماست:
          چقدر تمرین کرد، کجا قوی است و کجا کمک لازم دارد.
        </p>
      </Sheet>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
