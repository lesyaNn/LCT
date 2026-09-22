export function formatDateRu(isoDate: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(new Date(isoDate));
}

export function formatDateTimeRu(isoDate: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(isoDate));
}
