/** اشتراکِ هر فرزند و پرداخت‌ها — همان شکلِ `backend/apps/billing/views.py` */

export interface Plan {
  code: string;
  title: string;
  durationDays: number;
  months: number;
  priceToman: number;
  perMonthToman: number;
  /** صرفه در برابرِ خریدِ ماه‌به‌ماه (۰ برای ماهانه) */
  savingPercent: number;
  /** شناسه‌ی همین پلن در کافه‌بازار (خرید از اپِ اندروید) */
  bazaarSku?: string | null;
}

export interface Renewal {
  planCode: string;
  planTitle: string;
  amountToman: number;
  /** تمدید پشتِ دوره‌ی فعلی می‌نشیند؛ این تاریخِ شروعش است */
  startsFromFa: string;
}

export interface ChildSubscription {
  childId: string;
  childName: string;
  status: 'active' | 'free';
  planCode: string | null;
  planTitle: string;
  startsAt: string | null;
  endsAt: string | null;
  endsAtFa: string;
  daysLeft: number;
  totalDays: number;
  /** ۷ روز یا کمتر مانده */
  expiringSoon: boolean;
  /** اشتراکِ همیشگی (ادمین‌ها و حساب‌های گروهِ «اشتراکِ همیشگی») — بی‌تاریخِ پایان، بی‌تمدید */
  lifetime?: boolean;
  /** اشتراکِ کافه‌بازار که خودِ بازار هر دوره تمدیدش می‌کند (لغو فقط از خودِ بازار) */
  autoRenews?: boolean;
  /** صورت‌حسابِ تمدید: همان پلنِ آخرین خرید (برای کسی که هنوز نخریده null) */
  renewal: Renewal | null;
}

export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'expired';

export interface Payment {
  id: number;
  factorNumber: string;
  childId: string | null;
  childName: string;
  planCode: string;
  planTitle: string;
  amountToman: number;
  status: PaymentStatus;
  statusLabel: string;
  /** اشتراکِ هدیه از تیمِ لوکو (مبلغ صفر) */
  isGift?: boolean;
  gateway?: 'zibal' | 'vandar' | 'bazaar';
  createdAtFa: string;
  paidAtFa: string;
  transId: string;
  cardNumber: string;
  startsAtFa: string;
  endsAtFa: string;
  message: string;
}

export interface BazaarVerifyResult {
  payment: Payment;
  subscription: ChildSubscription;
}

export interface CheckoutResult {
  paymentId: number;
  factorNumber: string;
  amountToman: number;
  payUrl: string;
}
