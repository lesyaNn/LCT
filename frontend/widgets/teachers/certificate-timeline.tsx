'use client';

import { useMemo } from 'react';
import { formatDateRu } from '@/shared/lib/formatters';
import { certificateStatusLabels, expirationStatusIntent, type SemanticIntent } from '@/shared/lib/status-semantics';
import type { TeacherCertificate } from '@/shared/lib/universities-repository';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import styles from './certificate-timeline.module.css';

interface TimelineRange { start: number; end: number; today: number; }

function timestamp(value: string): number { return new Date(`${value}T00:00:00`).getTime(); }
function formatTimelineDate(value: number): string { return formatDateRu(new Date(value).toISOString()); }
function statusIntent(certificate: TeacherCertificate): SemanticIntent { return certificate.status === 'no_expiry' ? 'neutral' : expirationStatusIntent[certificate.status]; }

export function CertificateTimeline({ certificates }: { certificates: TeacherCertificate[] }) {
  const range = useMemo<TimelineRange | null>(() => {
    if (!certificates.length) return null;
    const today = new Date();
    const todayTimestamp = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const starts = certificates.map((certificate) => timestamp(certificate.issuedAt)).filter(Number.isFinite);
    const ends = certificates.map((certificate) => certificate.expiresAt ? timestamp(certificate.expiresAt) : todayTimestamp).filter(Number.isFinite);
    if (!starts.length) return null;
    const start = Math.min(...starts, todayTimestamp);
    const end = Math.max(...ends, todayTimestamp, start + 86_400_000);
    return { start, end, today: todayTimestamp };
  }, [certificates]);

  if (!range) return null;
  const span = range.end - range.start;
  const todayPosition = Math.max(0, Math.min(100, ((range.today - range.start) / span) * 100));
  return (
    <section className={styles.section} aria-labelledby="teacher-certificate-timeline-title">
      <div className={styles.heading}><div><h2 id="teacher-certificate-timeline-title">Сроки действия сертификатов</h2><p>Период действия показан от даты выдачи до окончания срока.</p></div></div>
      <div className={styles.surface}>
        <div className={styles.legend} aria-label="Обозначения timeline"><span><i className={styles.legendDot} />Актуален</span><span><i className={`${styles.legendDot} ${styles.legendWarning}`} />Скоро истекает</span><span><i className={`${styles.legendDot} ${styles.legendDanger}`} />Просрочен</span></div>
        <div className={styles.timelineViewport}>
          <div className={styles.timelineCanvas}>
            <div className={styles.axis}><span /><div className={styles.axisTrack}><span>{formatTimelineDate(range.start)}</span><span className={styles.todayLabel} style={{ left: `${todayPosition}%` }}>Сегодня</span><span>{formatTimelineDate(range.end)}</span></div></div>
            <div className={styles.rows}>
              {certificates.map((certificate) => {
                const start = timestamp(certificate.issuedAt);
                const end = certificate.expiresAt ? timestamp(certificate.expiresAt) : range.end;
                const left = Math.max(0, ((start - range.start) / span) * 100);
                const width = Math.max(1.5, ((end - start) / span) * 100);
                const statusText = certificateStatusLabels[certificate.status];
                const accessibleName = `${certificate.name}. Выдан ${formatDateRu(certificate.issuedAt)}. ${certificate.expiresAt ? `Истекает ${formatDateRu(certificate.expiresAt)}` : 'Бессрочный сертификат'}. ${statusText}. ${certificate.mandatory ? 'Обязательный.' : 'Не обязательный.'}`;
                return <div className={styles.row} key={certificate.id}><div className={styles.rowLabel}><strong>{certificate.name}</strong><span>{certificate.mandatory ? 'Обязательный' : 'Дополнительный'}</span></div><div className={styles.track}><span className={styles.todayLine} style={{ left: `${todayPosition}%` }} aria-hidden="true" /><Tooltip content={<><strong>{certificate.name}</strong><span>Выдан: {formatDateRu(certificate.issuedAt)}</span><span>Истекает: {certificate.expiresAt ? formatDateRu(certificate.expiresAt) : 'бессрочно'}</span><span>Статус: {statusText}</span><span>{certificate.mandatory ? 'Обязательный' : 'Не обязательный'}</span></>}><span className={`${styles.bar} ${certificate.mandatory ? styles.mandatory : ''} ${styles[statusIntent(certificate)]} ${certificate.expiresAt ? '' : styles.openEnded}`} style={{ left: `${left}%`, width: `${width}%` }} tabIndex={0} role="img" aria-label={accessibleName} /></Tooltip></div></div>;
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
