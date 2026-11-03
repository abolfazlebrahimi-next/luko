import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ROLE_HOME } from 'types/user';
import { useAuth } from '../../context';
import { authApi } from '../../api';
import { enableGuestMode } from '../../guest';
import styles from './OtpAuthForm.module.css';

/** ارقام فارسی/عربی → انگلیسی و حذفِ غیررقم */
function digits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
    .replace(/\D/g, '');
}

function errorMessage(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { error?: { message?: string } } } };
  return e?.response?.data?.error?.message ?? fallback;
}

interface Props {
  mode: 'login' | 'register';
}

export function OtpAuthForm({ mode }: Props) {
  const navigate = useNavigate();
  const referralCode = new URLSearchParams(window.location.search).get('ref') || '';
  const authQuery = referralCode ? `?ref=${encodeURIComponent(referralCode)}` : '';
  const { setUser } = useAuth();

  const [step, setStep] = useState<'phone' | 'code'>('phone');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [devCode, setDevCode] = useState<string | undefined>();
  const [resendIn, setResendIn] = useState(0);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // شمارش معکوسِ ارسالِ مجدد
  useEffect(() => {
    if (resendIn <= 0) return;
    const id = setInterval(() => setResendIn((n) => (n > 0 ? n - 1 : 0)), 1000);
    return () => clearInterval(id);
  }, [resendIn]);

  const sendOtp = async () => {
    setError('');
    setSubmitting(true);
    try {
      const res = await authApi.requestOtp(phone);
      setDevCode(res.devCode);
      setResendIn(res.resendIn);
      setStep('code');
    } catch (err) {
      setError(errorMessage(err, 'ارسال کد ناموفق بود؛ شماره را بررسی کن.'));
    } finally {
      setSubmitting(false);
    }
  };

  const verify = async () => {
    setError('');
    setSubmitting(true);
    try {
      const { user } = await authApi.verifyOtp({
        phone,
        code,
        role: referralCode ? 'parent' : undefined,
        referralCode: referralCode || undefined,
        firstName: mode === 'register' ? firstName : undefined,
        lastName: mode === 'register' ? lastName : undefined,
      });
      setUser(user);
      navigate(ROLE_HOME[user.role] ?? '/', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'کد اشتباه یا منقضی شده.'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    if (step === 'phone') void sendOtp();
    else void verify();
  };

  const enterAsGuest = () => {
    setUser(enableGuestMode());
    navigate('/', { replace: true });
  };

  const changeNumber = () => {
    setStep('phone');
    setCode('');
    setDevCode(undefined);
    setError('');
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <h1 className={styles.title}>لوکو</h1>
      <p className={styles.subtitle}>
        {referralCode ? 'ثبت‌نام یا ورود والد با لینک دعوت' : mode === 'register' ? 'ساخت حساب تازه' : 'شهر یادگیری و بازی!'}
      </p>

      {step === 'phone' ? (
        <>
          {mode === 'register' && (
            <div className={styles.row}>
              <input
                className={styles.input}
                placeholder="نام"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
              />
              <input
                className={styles.input}
                placeholder="نام خانوادگی"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </div>
          )}
          <input
            className={styles.input}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="شماره موبایل (۰۹...)"
            value={phone}
            onChange={(e) => setPhone(digits(e.target.value))}
            maxLength={11}
            required
          />
          <button type="submit" className={styles.submit} disabled={submitting}>
            {submitting ? 'در حال ارسال…' : 'ارسال کد'}
          </button>
        </>
      ) : (
        <>
          <p className={styles.hint}>
            کد به شماره‌ی <b dir="ltr">{phone}</b> پیامک شد
          </p>
          <input
            className={`${styles.input} ${styles.codeInput}`}
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="کد ۵ رقمی"
            value={code}
            onChange={(e) => setCode(digits(e.target.value))}
            maxLength={6}
            autoFocus
            required
          />
          {devCode && <p className={styles.devHint}>کدِ تست: {devCode}</p>}
          <button type="submit" className={styles.submit} disabled={submitting || code.length < 4}>
            {submitting ? 'در حال بررسی…' : mode === 'register' ? 'تایید و ثبت‌نام' : 'تایید و ورود'}
          </button>
          <button
            type="button"
            className={styles.link}
            onClick={() => void sendOtp()}
            disabled={resendIn > 0 || submitting}
          >
            {resendIn > 0
              ? `ارسال مجدد کد تا ${resendIn.toLocaleString('fa-IR')} ثانیه`
              : 'ارسال مجدد کد'}
          </button>
          <button type="button" className={styles.link} onClick={changeNumber}>
            تغییر شماره
          </button>
        </>
      )}

      {error && <p className={styles.error}>{error}</p>}

      {mode === 'login' && step === 'phone' && (
        <button type="button" className={styles.guest} onClick={enterAsGuest}>
          ورود به عنوان مهمان
        </button>
      )}

      <p className={styles.footer}>
        {mode === 'login' ? (
          <>
            حساب نداری؟ <Link to={`/register${authQuery}`}>ثبت‌نام</Link>
          </>
        ) : (
          <>
            حساب داری؟ <Link to={`/login${authQuery}`}>ورود</Link>
          </>
        )}
      </p>
    </form>
  );
}
