import { useEffect, useState } from 'react';
import { apiClient } from 'lib/api';
import { useQueryClient } from '@tanstack/react-query';
import type { Child } from '../../types';
import { Card, SectionTitle } from '../shell/Card';
import styles from './ReferralCard.module.css';

type Reward = { id: number; kind: string; days: number; redeemed: boolean };
type Referral = { code: string; invitedCount: number; rewards: Reward[] };

export function ReferralCard({ children }: { children: Child[] }) {
  const queryClient = useQueryClient();
  const [data, setData] = useState<Referral>();
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [child, setChild] = useState('');
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const response = await apiClient.get('/parent/referral');
      setData(response.data.data);
      setError('');
    } catch { setError('دریافت اطلاعات دعوت انجام نشد.'); }
  };
  useEffect(() => { void load(); }, []);
  const link = data ? `${window.location.origin}/register?ref=${encodeURIComponent(data.code)}` : '';
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); setMessage('لینک کپی شد.'); }
    catch { setMessage('لینک را از کادر انتخاب و کپی کنید.'); }
  };
  const redeem = async (id: number) => {
    setBusy(true); setMessage('');
    try {
      await apiClient.post(`/parent/referral/rewards/${id}/redeem`, { childId: child });
      await queryClient.invalidateQueries({ queryKey: ['parent'] });
      await load(); setMessage('پاداش به اشتراک فرزند اضافه شد.');
    } catch (err) {
      const e = err as { response?: { data?: { error?: { message?: string } } } };
      setMessage(e.response?.data?.error?.message || 'ثبت پاداش انجام نشد؛ دوباره تلاش کنید.');
    }
    finally { setBusy(false); }
  };
  return <>
    <SectionTitle>دعوت دوستان</SectionTitle>
    <Card>
      <div className={styles.content}>
        <b>دوستانتان را به لوکو دعوت کنید 🎁</b>
        <p>با ثبت‌نام والد جدید از لینک شما، هر دو ۳ روز اشتراک هدیه می‌گیرید. با اولین خرید موفق دوستتان، ۱۵ روز دیگر هدیه بگیرید.</p>
        {error && <p role="alert">{error} <button type="button" onClick={() => void load()}>تلاش دوباره</button></p>}
        {data && <>
          <label htmlFor="referral-link">لینک اختصاصی شما</label>
          <input id="referral-link" dir="ltr" readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
          <button type="button" onClick={() => void copy()}>کپی لینک</button>
          <p>تعداد دوستان ثبت‌نام‌کرده: {data.invitedCount.toLocaleString('fa-IR')}</p>
          <b>پاداش‌های شما</b>
          {!data.rewards.length && <p>هنوز پاداشی ندارید.</p>}
          {data.rewards.some((r) => !r.redeemed) && <>
            <label htmlFor="reward-child">فرزند دریافت‌کننده پاداش را انتخاب کنید</label>
            <select id="reward-child" value={child} onChange={(e) => setChild(e.target.value)}>
              <option value="">انتخاب فرزند</option>
              {children.map((c) => <option key={c.id} value={c.id}>{`${c.firstName} ${c.lastName}`.trim() || 'فرزند'}</option>)}
            </select>
            {!children.length && <p>ابتدا یک فرزند به حساب خود اضافه کنید.</p>}
          </>}
          {data.rewards.map((r) => <div className={styles.reward} key={r.id}>
            <span>{r.days.toLocaleString('fa-IR')} روز · {r.kind === 'purchase' ? 'خرید دوست' : 'دعوت دوستان'}</span>
            {r.redeemed ? <span>استفاده‌شده</span> : <button type="button" disabled={!child || busy} onClick={() => void redeem(r.id)}>افزودن به اشتراک</button>}
          </div>)}
        </>}
        {message && <p role="status">{message}</p>}
      </div>
    </Card>
  </>;
}
