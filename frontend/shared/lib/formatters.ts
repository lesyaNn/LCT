export function formatDateRu(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(date);
}

export function formatDateTimeRu(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export type ExpirationStatus = 'current' | 'expires_soon' | 'expired';

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
  const days = getDaysUntil(isoDate, now);
  if (days === null) return 'Срок не указан';
  if (days < 0) return `Просрочено на ${Math.abs(days)} ${pluralizeDays(Math.abs(days))}`;
  if (days === 0) return 'Истекает сегодня';
  return `Осталось ${days} ${pluralizeDays(days)}`;
}

function pluralizeDays(value: number): string {
  const remainder10 = value % 10;
  const remainder100 = value % 100;
  if (remainder10 === 1 && remainder100 !== 11) return 'день';
  if (remainder10 >= 2 && remainder10 <= 4 && (remainder100 < 10 || remainder100 >= 20)) return 'дня';
  return 'дней';
}
