'use client';

import { useSyncExternalStore } from 'react';
import Time from '@atomaro/icons/24/alert/TimeStroke';
import { localTimeAt } from '@/shared/lib/university-local-time';
import styles from './university-local-clock.module.css';

const listeners = new Set<() => void>();
let instant: number | null = null;
let timer: ReturnType<typeof setInterval> | undefined;
function update() {
  if (document.hidden) return;
  instant = Date.now();
  listeners.forEach(listener => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    instant = Date.now();
    timer = setInterval(update, 1000);
    document.addEventListener('visibilitychange', update);
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', update);
    }
  };
}
function getInstant() { return instant; }
function serverInstant() { return null; }

export function UniversityLocalClock({ city, timeZone }: { city: string; timeZone?: string | null }) {
  const now = useSyncExternalStore(subscribe, getInstant, serverInstant);
  const local = now === null ? null : localTimeAt(timeZone, now);
  if (!timeZone || (now !== null && !local)) return <span className={styles.unknown}>Местное время не определено</span>;
  return <div className={styles.clock} role="group" aria-label="Местное время вуза">
    <Time size={18} fill="currentColor" />
    <div><span className={styles.caption}>Местное время{city && city !== '—' ? `, ${city}` : ''}</span>
      <div className={styles.reading}><time className={styles.time} dateTime={now === null ? undefined : new Date(now).toISOString()}>{local?.time ?? '--:--:--'}</time><span>{local ? `${local.date} · ${local.offset}` : timeZone}</span></div>
      {local?.outsideDaytime ? <span className={styles.hint} title="Ориентир для звонков. Фактический график вуза может отличаться.">Сейчас вне 09:00-18:00</span> : null}
    </div>
  </div>;
}
