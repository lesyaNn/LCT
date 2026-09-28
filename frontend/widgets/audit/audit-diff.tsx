import type { AuditEvent } from '@/shared/lib/audit-repository';import { summarizeAuditEvent } from '@/shared/lib/audit-human';
import styles from './audit-diff.module.css';

type AuditDiffSource = {
  oldValues?: unknown;
  newValues?: unknown;
  requestId?: string;
  ip?: string;
  userAgent?: string;
  action?: string;
  entity?: { id?: string; type?: string };
  university?: { name?: string };
  user?: { name?: string };
  role?: string;
  presentation?: unknown | null;
};

function toAuditEvent(event: AuditDiffSource): AuditEvent {
  return {
    id: '',
    occurredAt: '',
    user: { id: '', name: typeof event.user?.name === 'string' ? event.user.name : '' },
    role: event.role,
    action: typeof event.action === 'string' ? event.action : 'UNKNOWN',
    entity: {
      id: typeof event.entity?.id === 'string' ? event.entity.id : '',
      type: typeof event.entity?.type === 'string' ? event.entity.type : 'unknown',
      label: '',
    },
    university: { id: '', name: typeof event.university?.name === 'string' ? event.university.name : '—' },
    oldValues: event.oldValues as AuditEvent['oldValues'],
    newValues: event.newValues as AuditEvent['newValues'],
    requestId: event.requestId,
    ip: event.ip,
    userAgent: event.userAgent,
    presentation: event.presentation ?? null,
  };
}

export function AuditDiff({ event, showTechnical = true }: { event: AuditDiffSource; showTechnical?: boolean }) {
  const summary = summarizeAuditEvent(toAuditEvent(event));
  const hasValues = event.oldValues !== undefined || event.newValues !== undefined;
  const technicalId = typeof event.entity?.id === 'string' && event.entity.id ? event.entity.id : null;

  return (
    <div className={styles.root}>
      {summary.note ? <p className={styles.note}>{summary.note}</p> : null}
      {summary.changes.length ? (
        <div className={styles.tableWrap}>
          <table>
            <thead><tr><th scope="col">Поле</th><th scope="col">Было</th><th scope="col">Стало</th></tr></thead>
            <tbody>{summary.changes.map((change) => <tr key={change.field}><th scope="row">{change.label}</th><td>{change.old}</td><td>{change.next}</td></tr>)}</tbody>
          </table>
        </div>
      ) : hasValues ? (
        <p className={styles.muted}>Изменений в полях нет.</p>
      ) : <p className={styles.muted}>Данные до/после изменения не переданы.</p>}
      {showTechnical && (event.requestId || event.ip || event.userAgent || technicalId) ? (
        <details className={styles.technical}>
          <summary>Техническая информация</summary>
          <dl>
            {technicalId ? <div><dt>Идентификатор записи</dt><dd>{technicalId}</dd></div> : null}
            {event.requestId ? <div><dt>Request ID</dt><dd>{event.requestId}</dd></div> : null}
            {event.ip ? <div><dt>IP</dt><dd>{event.ip}</dd></div> : null}
            {event.userAgent ? <div><dt>User-Agent</dt><dd>{event.userAgent}</dd></div> : null}
          </dl>
        </details>
      ) : null}
    </div>
  );
}
