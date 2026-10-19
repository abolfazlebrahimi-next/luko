/** شکلِ داده‌ی بخش‌های تنظیمات — همان `apps/parent/account.py` و `apps/support/serializers.py` */

export interface ChildProfile {
  id: string;
  firstName: string;
  lastName: string;
  phone: string;
  phoneVerified: boolean;
  grade: number;
  /** «پایه‌ی دوم» */
  gradeLabel: string;
  school: string;
  /** «والد» / «سرپرست» */
  relation: string;
  joinedFa: string;
  joinedDays: number;
  linkedFa: string;
  /** «امروز، ۱۸:۳۷» یا خالی */
  lastSeenFa: string;
  platform: 'web' | 'android' | '';
  online: boolean;
  stats: {
    coins: number;
    points: number;
    treasures: number;
    gamesCompleted: number;
    medals: number;
    tasks: number;
    streak: number;
    paintings: number;
    checkins: number;
  };
  subscription: { active: boolean; lifetime?: boolean; planTitle: string; daysLeft: number; endsFa: string };
}

export type TicketStatus = 'open' | 'answered' | 'closed';
export type TicketCategory = 'account' | 'billing' | 'reports' | 'games' | 'technical' | 'idea' | 'other';

export interface TicketSummary {
  id: number;
  /** شماره‌ی پیگیری: LK-1042 */
  code: string;
  subject: string;
  category: TicketCategory;
  categoryLabel: string;
  status: TicketStatus;
  statusLabel: string;
  priority: 'normal' | 'high';
  childId: string | null;
  childName: string;
  createdFa: string;
  lastFa: string;
  preview: string;
  lastFromStaff: boolean;
  messages: number;
  /** پاسخ‌های تیم بعد از آخرین بازدید */
  unread: number;
  rating: number | null;
}

export interface TicketDetail extends TicketSummary {
  closedFa: string;
  ratingComment: string;
  canReply: boolean;
  canClose: boolean;
  canRate: boolean;
  thread: { id: number; body: string; fromStaff: boolean; sender: string; atFa: string }[];
}

export interface TicketList {
  items: TicketSummary[];
  counts: { all: number; open: number; answered: number; closed: number };
  unread: number;
  categories: { key: TicketCategory; label: string }[];
  /** والدِ مشترک: تیکت‌هایش اولویتِ بالا دارند */
  priority: boolean;
}

export interface NewTicket {
  category: TicketCategory;
  childId?: string | null;
  subject: string;
  body: string;
}
