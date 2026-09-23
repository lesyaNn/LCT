import type { AuditEvent, AuditJsonValue } from '@/shared/lib/audit-repository';
import { isAuditJsonObject } from '@/shared/lib/audit-repository';
import styles from './audit-diff.module.css';

type AuditDiffSource = Pick<AuditEvent, 'oldValues' | 'newValues' | 'requestId' | 'ip' | 'userAgent'>;

function valueAsJson(value: AuditJsonValue | undefined): string {
  if (value === undefined) return '—';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

export function AuditDiff({ event }: { event: AuditDiffSource }) {
  const oldObject = isAuditJsonObject(event.oldValues) ? event.oldValues : null;
  const newObject = isAuditJsonObject(event.newValues) ? event.newValues : null;
  const keys = [...new Set([...Object.keys(oldObject ?? {}), ...Object.keys(newObject ?? {})])];
  const hasValues = event.oldValues !== undefined || event.newValues !== undefined;

  return (
    <div className={styles.root}>
      {keys.length ? (
        <div className={styles.tableWrap}>
          <table>
            <thead><tr><th scope="col">Поле</th><th scope="col">Было</th><th scope="col">Стало</th></tr></thead>
            <tbody>{keys.map((key) => <tr key={key}><th scope="row">{key}</th><td>{valueAsJson(oldObject?.[key])}</td><td>{valueAsJson(newObject?.[key])}</td></tr>)}</tbody>
          </table>
        </div>
      ) : hasValues ? (
        <div className={styles.jsonGrid}><div><span>Было</span><pre>{valueAsJson(event.oldValues)}</pre></div><div><span>Стало</span><pre>{valueAsJson(event.newValues)}</pre></div></div>
      ) : <p className={styles.muted}>Данные до/после изменения не переданы.</p>}
      {event.requestId || event.ip || event.userAgent ? (
        <dl className={styles.technical}>
          {event.requestId ? <div><dt>Request ID</dt><dd>{event.requestId}</dd></div> : null}
          {event.ip ? <div><dt>IP</dt><dd>{event.ip}</dd></div> : null}
          {event.userAgent ? <div><dt>User-Agent</dt><dd>{event.userAgent}</dd></div> : null}
        </dl>
      ) : null}
    </div>
  );
}
