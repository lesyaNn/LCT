export function formatDateRu(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(date);
}

export function formatDateTimeRu(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export type ExpirationStatus = 'current' | 'expires_soon' | 'expired';
export type UpcomingDateStatus = 'long_term' | 'approaching' | 'urgent' | 'overdue' | 'unknown';

export function getDaysUntil(isoDate: string, now = new Date()): number | null {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return null;
  const startOfDay = (value: Date) => Date.UTC(value.getFullYear(), value.getMonth(), value.getDate());
  return Math.ceil((startOfDay(date) - startOfDay(now)) / 86_400_000);
}

export function getExpirationStatus(isoDate: string, soonDays = 45, now = new Date()): ExpirationStatus {
  const daysUntil = getDaysUntil(isoDate, now);
  if (daysUntil === null || daysUntil < 0) return 'expired';
  return daysUntil <= soonDays ? 'expires_soon' : 'current';
}

export function formatDaysUntilRu(isoDate: string, now = new Date()): string {
  const relative = getRelativeDueDateRu(isoDate, now);
  if (relative.days === 0) return 'Истекает сегодня';
  return relative.overdueLabel ?? relative.label;
}

export interface RelativeDueDateRu {
  days: number | null;
  label: string;
  overdueLabel: string | null;
  dueSoonLabel: string | null;
}

/** Shared Russian relative date presentation for workflow and other deadline UI. */
export function getRelativeDueDateRu(isoDate: string, now = new Date()): RelativeDueDateRu {
  const days = getDaysUntil(isoDate, now);
  if (days === null) return { days: null, label: 'Срок не указан', overdueLabel: null, dueSoonLabel: null };
  if (days < 0) {
    const absoluteDays = Math.abs(days);
    return {
      days,
      label: absoluteDays === 1 ? 'Вчера' : `${absoluteDays} ${pluralizeDays(absoluteDays)} назад`,
      overdueLabel: `Просрочено на ${absoluteDays} ${pluralizeDays(absoluteDays)}`,
      dueSoonLabel: null,
    };
  }
  if (days === 0) return { days, label: 'Сегодня', overdueLabel: null, dueSoonLabel: 'Срочно: сегодня' };
  if (days === 1) return { days, label: 'Завтра', overdueLabel: null, dueSoonLabel: 'Срочно: завтра' };
  const relative = `Через ${days} ${pluralizeDays(days)}`;
  return { days, label: relative, overdueLabel: null, dueSoonLabel: days <= 3 ? `Срочно: ${relative.toLocaleLowerCase('ru-RU')}` : null };
}

export function getUpcomingDateStatus(isoDate: string | null, now = new Date()): UpcomingDateStatus {
  if (!isoDate) return 'unknown';
  const days = getDaysUntil(isoDate, now);
  if (days === null) return 'unknown';
  if (days < 0) return 'overdue';
  if (days < 30) return 'urgent';
  if (days <= 90) return 'approaching';
  return 'long_term';
}

function pluralizeDays(value: number): string {
  const remainder10 = value % 10;
  const remainder100 = value % 100;
  if (remainder10 === 1 && remainder100 !== 11) return 'день';
  if (remainder10 >= 2 && remainder10 <= 4 && (remainder100 < 10 || remainder100 >= 20)) return 'дня';
  return 'дней';
}
