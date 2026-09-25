export type PeriodPreset = 'current_month' | 'current_quarter' | 'current_year' | 'previous_year';

function localIsoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function periodPresetRange(preset: PeriodPreset, now = new Date()): { dateFrom: string; dateTo: string } {
  const year = now.getFullYear();
  const month = now.getMonth();
  if (preset === 'current_month') return { dateFrom: localIsoDate(new Date(year, month, 1)), dateTo: localIsoDate(new Date(year, month + 1, 0)) };
  if (preset === 'current_quarter') {
    const firstMonth = Math.floor(month / 3) * 3;
    return { dateFrom: localIsoDate(new Date(year, firstMonth, 1)), dateTo: localIsoDate(new Date(year, firstMonth + 3, 0)) };
  }
  if (preset === 'current_year') return { dateFrom: localIsoDate(new Date(year, 0, 1)), dateTo: localIsoDate(new Date(year, 11, 31)) };
  return { dateFrom: localIsoDate(new Date(year - 1, 0, 1)), dateTo: localIsoDate(new Date(year - 1, 11, 31)) };
}

export const periodPresetOptions: ReadonlyArray<{ id: PeriodPreset; label: string }> = [
  { id: 'current_month', label: 'Текущий месяц' },
  { id: 'current_quarter', label: 'Текущий квартал' },
  { id: 'current_year', label: 'Текущий год' },
  { id: 'previous_year', label: 'Прошлый год' },
];
