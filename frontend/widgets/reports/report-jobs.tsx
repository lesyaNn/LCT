'use client';

import CheckStatistics from '@atomaro/icons/24/action/CheckStatistics';
import CloudDownload from '@atomaro/icons/24/action/CloudDownload';
import RefreshSmall from '@atomaro/icons/24/action/RefreshSmall';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import { useState, type ReactNode } from 'react';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { ErrorState } from '@/shared/ui/error-state';
import { Progress } from '@/shared/ui/rtk/progress';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableSkeleton } from '@/shared/ui/skeleton';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { formatDateTimeRu, formatFileSize } from '@/shared/lib/formatters';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { type SemanticIntent } from '@/shared/lib/status-semantics';
import { REPORTS_API_CAPABILITIES, downloadReportJob, type ReportJob, type ReportJobStatus } from '@/shared/lib/reports-repository';
import styles from './reports-page.module.css';

/** A job still being produced; polling continues until it is terminal. */
export const REPORT_JOB_TIMEOUT_MS = 60_000;

const statusMeta: Record<ReportJobStatus, { label: string; intent: SemanticIntent; icon: ReactNode }> = {
  queued: { label: 'В очереди', intent: 'neutral', icon: <TimeStroke size={14} fill="currentColor" aria-hidden="true" /> },
  building: { label: 'Формируется', intent: 'info', icon: <InformationStroke size={14} fill="currentColor" aria-hidden="true" /> },
  ready: { label: 'Готов', intent: 'success', icon: <CheckStatistics size={14} fill="currentColor" aria-hidden="true" /> },
  failed: { label: 'Ошибка', intent: 'danger', icon: <ErrorStroke size={14} fill="currentColor" aria-hidden="true" /> },
};

export function isActiveJob(job: ReportJob): boolean {
  return job.status === 'queued' || job.status === 'building';
}

/** Slow-job hint; the status keeps updating, this is not a timeout. */
export function isSlowJob(job: ReportJob): boolean {
  if (!isActiveJob(job)) return false;
  const createdAt = Date.parse(job.createdAt);
  return Number.isFinite(createdAt) && Date.now() - createdAt >= REPORT_JOB_TIMEOUT_MS;
}

function JobStatus({ status }: { status: ReportJobStatus }) {
  const meta = statusMeta[status];
  return <StatusBadge intent={meta.intent} icon={meta.icon}>{meta.label}</StatusBadge>;
}

function JobProgress({ job }: { job: ReportJob }) {
  if (job.status !== 'building' && job.status !== 'ready') return <span className={styles.muted}>—</span>;
  return (
    <div className={styles.progressCell}>
      <Progress value={job.progress ?? 0} label={`Прогресс отчёта ${job.name}`} />
      <span>{job.status === 'ready' ? '100%' : job.progress === null ? 'Выполняется' : `${job.progress}%`}</span>
    </div>
  );
}

function JobStateDetails({ job, timedOut, pollingError, retryError }: { job: ReportJob; timedOut: boolean; pollingError?: string; retryError?: string }) {
  if (job.status === 'failed') return <p className={styles.jobError}>{job.error ?? 'Не удалось сформировать отчёт.'}</p>;
  if (retryError) return <p className={styles.jobActionError} role="alert">{retryError}</p>;
  if (timedOut && isActiveJob(job)) return <p className={styles.timeoutMessage}>Формирование занимает больше минуты — продолжаем отслеживать статус автоматически.</p>;
  if (pollingError) return <p className={styles.pollingError}>Не удалось обновить статус. Повторяем попытку…</p>;
  return null;
}

function JobActions({ job, timedOut, retrying, onRetry }: { job: ReportJob; timedOut: boolean; retrying: boolean; onRetry: (job: ReportJob) => void }) {
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const download = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const blob = await downloadReportJob(job.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `report_${job.id}.${job.format}`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (cause) {
      setDownloadError(normalizeApiError(cause, { fallbackMessage: 'Не удалось скачать отчёт.' }).message);
    } finally {
      setDownloading(false);
    }
  };

  if (job.status === 'ready') {
    // Mock data source hands back an inline data: URL; the real API is fetched.
    if (job.downloadUrl?.startsWith('data:')) {
      return <a className={styles.actionLink} href={job.downloadUrl} download={`${job.name}.${job.format}`} aria-label={`Скачать ${job.name}`}><CloudDownload size={16} fill="currentColor" />Скачать</a>;
    }
    if (job.downloadUrl) {
      return (
        <>
          <Button variant="ghost" size="s" type="button" loading={downloading} onClick={() => void download()}>
            <CloudDownload size={16} fill="currentColor" />Скачать
          </Button>
          {downloadError ? <span role="alert" className={styles.jobActionError}>{downloadError}</span> : null}
        </>
      );
    }
    return <span className={styles.actionUnavailable} title="Сервер не вернул download_url">Файл недоступен</span>;
  }

  if ((job.status === 'failed' || timedOut) && REPORTS_API_CAPABILITIES.retry && job.request) {
    return (
      <Button variant="ghost" size="s" type="button" onClick={() => onRetry(job)} loading={retrying} disabled={retrying} aria-label={`Повторить ${job.name}`}>
        {retrying ? null : <RefreshSmall size={16} fill="currentColor" />}Повторить
      </Button>
    );
  }
  return null;
}

interface JobViewProps {
  job: ReportJob;
  pollingError?: string;
  retryError?: string;
  retrying: boolean;
  onRetry: (job: ReportJob) => void;
}

function ReportJobRow({ job, pollingError, retryError, retrying, onRetry }: JobViewProps) {
  const timedOut = isSlowJob(job);
  return (
    <tr data-testid={`report-job-${job.id}`}>
      <td>
        <strong>{job.name}</strong>
        <JobStateDetails job={job} timedOut={timedOut} pollingError={pollingError} retryError={retryError} />
      </td>
      <td>{job.format.toUpperCase()}</td>
      <td>
        <JobStatus status={job.status} />
        {job.error && job.status === 'failed' ? (
          <Tooltip content={<span>{job.error}</span>}>
            <span className={styles.errorHint} tabIndex={0}>Подробнее</span>
          </Tooltip>
        ) : null}
      </td>
      <td><JobProgress job={job} /></td>
      <td>
        <time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time>
        {job.expiresAt ? <><br /><small className={styles.muted}>Доступен до {formatDateTimeRu(job.expiresAt)}</small></> : null}
        {typeof job.fileSize === 'number' ? <><br /><small className={styles.muted}>{formatFileSize(job.fileSize)}</small></> : null}
      </td>
      <td>
        <div className={styles.jobActions}>
          <JobActions job={job} timedOut={timedOut} retrying={retrying} onRetry={onRetry} />
        </div>
      </td>
    </tr>
  );
}

function ReportJobCard({ job, pollingError, retryError, retrying, onRetry }: JobViewProps) {
  const timedOut = isSlowJob(job);
  return (
    <article className={styles.jobCard}>
      <div className={styles.jobCardHeader}><strong>{job.name}</strong><JobStatus status={job.status} /></div>
      <dl>
        <div><dt>Формат</dt><dd>{job.format.toUpperCase()}</dd></div>
        <div>
          <dt>Создан</dt>
          <dd>
            <time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time>
            {job.expiresAt ? <> · доступен до {formatDateTimeRu(job.expiresAt)}</> : null}
            {typeof job.fileSize === 'number' ? <> · {formatFileSize(job.fileSize)}</> : null}
          </dd>
        </div>
        <div><dt>Прогресс</dt><dd><JobProgress job={job} /></dd></div>
      </dl>
      <JobStateDetails job={job} timedOut={timedOut} pollingError={pollingError} retryError={retryError} />
      <div className={styles.jobCardActions}><JobActions job={job} timedOut={timedOut} retrying={retrying} onRetry={onRetry} /></div>
    </article>
  );
}

interface ReportJobsPanelProps {
  jobs: ReportJob[];
  loading: boolean;
  error: unknown;
  pollingErrors: ReadonlyMap<string, string>;
  retryErrors: ReadonlyMap<string, string>;
  retryingId: string | null;
  onRetry: (job: ReportJob) => void;
  onRefresh: () => void;
}

export function ReportJobsPanel({ jobs, loading, error, pollingErrors, retryErrors, retryingId, onRetry, onRefresh }: ReportJobsPanelProps) {
  if (loading) return <TableSkeleton rows={4} columns={6} label="Загрузка задач отчётов" />;
  if (error) {
    const normalized = normalizeApiError(error, { fallbackMessage: 'Не удалось загрузить задачи отчётов.' });
    return <ErrorState title={normalized.message} description="Попробуйте повторить запрос." headingLevel={3} onRetry={onRefresh} />;
  }
  if (!jobs.length) return <EmptyState title="Отчёты ещё не формировались" description="Созданные задачи появятся здесь." headingLevel={3} />;

  return (
    <div aria-label="Задачи отчётов" className={styles.jobsListShell} tabIndex={0}>
      <div className={styles.jobsDesktop}>
        <table>
          <caption className={styles.visuallyHidden}>Задачи отчётов</caption>
          <thead>
            <tr>
              <th scope="col">Отчёт</th><th scope="col">Формат</th><th scope="col">Статус</th>
              <th scope="col">Прогресс</th><th scope="col">Создан</th><th scope="col">Действия</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <ReportJobRow key={job.id} job={job} pollingError={pollingErrors.get(job.id)} retryError={retryErrors.get(job.id)} retrying={retryingId === job.id} onRetry={onRetry} />
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.jobsMobile}>
        {jobs.map((job) => (
          <ReportJobCard key={job.id} job={job} pollingError={pollingErrors.get(job.id)} retryError={retryErrors.get(job.id)} retrying={retryingId === job.id} onRetry={onRetry} />
        ))}
      </div>
    </div>
  );
}
