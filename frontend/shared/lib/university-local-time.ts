export function localTimeAt(timeZone: string | null | undefined, now: number) {
  if (!timeZone) return null;
  try {
    const parts = new Intl.DateTimeFormat('ru-RU', {
      timeZone, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
      day: '2-digit', month: '2-digit', year: 'numeric', timeZoneName: 'shortOffset',
    }).formatToParts(now);
    const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(value => value.type === type)?.value ?? '';
    const hour = Number(part('hour'));
    return {
      time: `${part('hour')}:${part('minute')}:${part('second')}`,
      date: `${part('day')}.${part('month')}.${part('year')}`,
      offset: part('timeZoneName').replace('GMT', 'UTC'),
      outsideDaytime: hour < 9 || hour >= 18,
    };
  } catch {
    return null;
  }
}

export function contactText(person: { name: string; role?: string; email?: string; phone?: string }) {
  return [person.name, person.role, person.email, person.phone].filter(value => value?.trim() && value.trim() !== '—').join('\n');
}
