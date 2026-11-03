import { apiClient, tokenStorage } from 'lib/api';
import type { User } from 'types/user';

export interface RequestOtpResult {
  /** اعتبارِ کد (ثانیه) */
  expiresIn: number;
  /** تا ارسالِ مجدد (ثانیه) */
  resendIn: number;
  /** فقط در حالتِ توسعه: کدِ تست */
  devCode?: string;
}

export interface VerifyOtpPayload {
  phone: string;
  code: string;
  firstName?: string;
  lastName?: string;
  role?: 'parent';
  referralCode?: string;
}

export interface VerifyOtpResult {
  user: User;
  /** حسابِ تازه ساخته شد؟ */
  isNew: boolean;
}

export const authApi = {
  /** گام ۱: ارسالِ رمزِ یکبارمصرف به شماره */
  async requestOtp(phone: string): Promise<RequestOtpResult> {
    const { data } = await apiClient.post('/auth/request-otp', { phone });
    return data.data;
  },

  /** گام ۲: بررسیِ کد؛ اگر حساب نبود ساخته می‌شود */
  async verifyOtp(payload: VerifyOtpPayload): Promise<VerifyOtpResult> {
    const { data } = await apiClient.post('/auth/verify-otp', payload);
    tokenStorage.set(data.data.accessToken);
    return { user: data.data.user, isNew: data.data.isNew };
  },

  async getCurrentUser(): Promise<User> {
    const { data } = await apiClient.get('/auth/me');
    return data.data;
  },

  logout() {
    tokenStorage.clear();
  },
};
