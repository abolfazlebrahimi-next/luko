import { apiClient } from 'lib/api';
import { demoParentApi, isGuestParentPreview } from './demoMode';
import type { Child, ChildReport, ParentNotification, ParentPreferences, Suggestion } from './types';

export interface Assignment {
  id: number;
  gameSlug: string;
  gameTitle: string;
  bookTitle: string;
  date: string;
  note: string;
  played: boolean;
}

export interface CatalogGame {
  slug: string;
  title: string;
  bookTitle: string;
  subject: string;
  coinReward: number;
}

export interface Ticket {
  id: number;
  subject: string;
  status: 'open' | 'answered' | 'closed';
  createdAt: string;
  lastMessageAt: string;
  messages: {
    id: number;
    body: string;
    isStaffReply: boolean;
    senderName: string;
    createdAt: string;
  }[];
}

/** همه‌ی درخواست‌های پنل والدین. پاکتِ {data} در همین‌جا باز می‌شود. */
export const parentApi = {
  async children(): Promise<Child[]> {
    if (isGuestParentPreview()) return demoParentApi.children();
    const { data } = await apiClient.get('/parent/children');
    return data.data;
  },

  async addChild(payload: {
    phone: string;
    password: string;
    firstName?: string;
    lastName?: string;
    grade?: number;
    school?: string;
  }): Promise<Child> {
    const { data } = await apiClient.post('/parent/children', payload);
    return data.data;
  },

  async removeChild(childId: string): Promise<void> {
    await apiClient.delete(`/parent/children/${childId}`);
  },

  async report(childId: string): Promise<ChildReport> {
    if (isGuestParentPreview()) return demoParentApi.report(childId);
    const { data } = await apiClient.get(`/parent/children/${childId}/report`);
    return data.data;
  },

  async assignments(childId: string, history = false): Promise<Assignment[]> {
    if (isGuestParentPreview()) return demoParentApi.assignments();
    const { data } = await apiClient.get(
      `/parent/children/${childId}/assignments${history ? '?history=1' : ''}`,
    );
    return data.data;
  },

  async setAssignment(
    childId: string,
    payload: { gameSlug: string; date: string; note?: string },
  ): Promise<Assignment> {
    if (isGuestParentPreview()) {
      return { id: 0, gameSlug: payload.gameSlug, gameTitle: 'بازی نمونه', bookTitle: 'نمونه',
        date: payload.date, note: payload.note ?? '', played: false };
    }
    const { data } = await apiClient.post(`/parent/children/${childId}/assignments`, payload);
    return data.data;
  },

  async removeAssignment(childId: string, id: number): Promise<void> {
    await apiClient.delete(`/parent/children/${childId}/assignments/${id}`);
  },

  /** کاتالوگ بازی‌ها برای انتخابگرِ «بازی روز» */
  async catalog(): Promise<CatalogGame[]> {
    if (isGuestParentPreview()) return demoParentApi.catalog();
    const { data } = await apiClient.get('/books');
    const books = data.data.books as {
      title: string;
      subject: string;
      levels: { slug: string; title: string; coinReward: number }[];
    }[];
    return books.flatMap((book) =>
      book.levels.map((level) => ({
        slug: level.slug,
        title: level.title,
        bookTitle: book.title,
        subject: book.subject,
        coinReward: level.coinReward,
      })),
    );
  },

  async tickets(): Promise<Ticket[]> {
    if (isGuestParentPreview()) return demoParentApi.tickets();
    const { data } = await apiClient.get('/tickets');
    return data.data;
  },

  async createTicket(payload: { subject: string; body: string }): Promise<Ticket> {
    const { data } = await apiClient.post('/tickets', payload);
    return data.data;
  },

  async replyTicket(id: number, body: string): Promise<void> {
    await apiClient.post(`/tickets/${id}/reply`, { body });
  },

  /** پیشنهادِ بازی روز — بر اساسِ ضعیف‌ترین مبحثِ همین بچه */
  async suggestions(childId: string): Promise<{
    date: string;
    currentSlug: string | null;
    suggestions: Suggestion[];
  }> {
    if (isGuestParentPreview()) return demoParentApi.suggestions();
    const { data } = await apiClient.get(`/parent/children/${childId}/suggestions`);
    return data.data;
  },

  async preferences(): Promise<ParentPreferences> {
    if (isGuestParentPreview()) return demoParentApi.preferences();
    const { data } = await apiClient.get('/parent/preferences');
    return data.data;
  },

  async setPreferences(payload: Partial<ParentPreferences>): Promise<ParentPreferences> {
    if (isGuestParentPreview()) {
      return { weeklyReport: true, activityAlerts: true, ...payload };
    }
    const { data } = await apiClient.patch('/parent/preferences', payload);
    return data.data;
  },

  async notifications(): Promise<{ items: ParentNotification[]; unread: number }> {
    if (isGuestParentPreview()) return demoParentApi.notifications();
    const { data } = await apiClient.get('/parent/notifications');
    return data.data;
  },

  async markNotificationsRead(): Promise<void> {
    if (isGuestParentPreview()) return;
    await apiClient.post('/parent/notifications/read');
  },
};
