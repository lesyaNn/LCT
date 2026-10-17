const daytimeStartHour = 9;
const daytimeEndHour = 18;

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
      outsideDaytime: hour < daytimeStartHour || hour >= daytimeEndHour,
      daytimeHours: `${String(daytimeStartHour).padStart(2, '0')}:00–${String(daytimeEndHour).padStart(2, '0')}:00`,
    };
  } catch {
    return null;
  }
}
