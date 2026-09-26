'use client';

import CheckStatistics from '@atomaro/icons/24/action/CheckStatistics';
import CloudDownload from '@atomaro/icons/24/action/CloudDownload';
import Filter from '@atomaro/icons/24/action/Filter';
import RefreshSmall from '@atomaro/icons/24/action/RefreshSmall';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import { zodResolver } from '@hookform/resolvers/zod';
import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState, type ReactNode } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';
import { applyServerErrorsToForm, normalizeApiError } from '@/shared/lib/api-errors';
import { formatDateTimeRu } from '@/shared/lib/formatters';
import { type SemanticIntent } from '@/shared/lib/status-semantics';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { ErrorState } from '@/shared/ui/error-state';
import { FormError, FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { DateRangeField } from '@/shared/ui/rtk/date-range-field';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import type { ActiveFilterItem } from '@/shared/ui/rtk/active-filters';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { Progress } from '@/shared/ui/rtk/progress';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { TableSkeleton } from '@/shared/ui/skeleton';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import {
  EMPTY_REPORT_FORM,
  REPORTS_API_CAPABILITIES,
  REPORT_FORMATS,
  createReportJob,
  downloadReportJob,
  getReportFilterOptions,
  getReportJob,
  listReportJobs,
  reportColumnDefinitions,
  reportColumnPresetNames,
  reportColumnPresets,
  reportFilterOptions,
  reportQueryKeys,
  reportRequestFromForm,
  retryReportJob,
  type ReportJob,
  type ReportJobStatus,
} from '@/shared/lib/reports-repository';
import styles from './reports-page.module.css';

const reportFields = ['dateFrom', 'dateTo', 'universityIds', 'directionIds', 'productIds', 'responsibleIds', 'workflowStatuses', 'columnIds', 'format'] as const;
const REPORT_JOB_TIMEOUT_MS = 60_000;
export { REPORT_JOB_TIMEOUT_MS };

const reportSchema = z.object({
  dateFrom: z.string(),
  dateTo: z.string(),
  universityIds: z.array(z.string()),
  directionIds: z.array(z.string()),
  productIds: z.array(z.string()),
  responsibleIds: z.array(z.string()),
  workflowStatuses: z.array(z.enum(['pending', 'current', 'completed', 'skipped', 'overdue'])),
  columnIds: z.array(z.string()).min(1, 'Выберите хотя бы одну колонку.'),
  format: z.enum(['xlsx', 'pdf', 'json']),
}).superRefine((values, context) => {
  if (values.dateFrom && values.dateTo && values.dateFrom > values.dateTo) context.addIssue({ code: z.ZodIssueCode.custom, path: ['dateTo'], message: 'Дата окончания не может быть раньше даты начала.' });
});

type ReportFormSchema = z.infer<typeof reportSchema>;

const statusMeta: Record<ReportJobStatus, { label: string; intent: SemanticIntent; icon: ReactNode }> = {
  queued: { label: 'В очереди', intent: 'neutral', icon: <TimeStroke size={14} fill="currentColor" aria-hidden="true" /> },
  building: { label: 'Формируется', intent: 'info', icon: <InformationStroke size={14} fill="currentColor" aria-hidden="true" /> },
  ready: { label: 'Готов', intent: 'success', icon: <CheckStatistics size={14} fill="currentColor" aria-hidden="true" /> },
  failed: { label: 'Ошибка', intent: 'danger', icon: <ErrorStroke size={14} fill="currentColor" aria-hidden="true" /> },
};

function isActiveJob(job: ReportJob): boolean {
  return job.status === 'queued' || job.status === 'building';
}

function hasTimedOut(job: ReportJob): boolean {
  if (!isActiveJob(job)) return false;
  const createdAt = Date.parse(job.createdAt);
  return Number.isFinite(createdAt) && Date.now() - createdAt >= REPORT_JOB_TIMEOUT_MS;
}

function JobStatus({ status }: { status: ReportJobStatus }) {
  const meta = statusMeta[status];
  return <StatusBadge intent={meta.intent} icon={meta.icon}>{meta.label}</StatusBadge>;
}

function JobProgress({ job, timedOut }: { job: ReportJob; timedOut: boolean }) {
  if (timedOut) return <span className={styles.timeoutProgress}>Ожидание прервано</span>;
  if (job.status === 'ready' && job.progress !== null) return <div className={styles.progressCell}><Progress value={job.progress} label={`Прогресс отчёта ${job.name}`} /><span>{job.progress}%</span></div>;
  if (job.status !== 'building') return <span className={styles.muted}>—</span>;
  return <div className={styles.progressCell}><Progress value={job.progress} label={`Прогресс отчёта ${job.name}`} /><span>{job.progress === null ? 'Выполняется' : `${job.progress}%`}</span></div>;
}

function JobStateDetails({ job, timedOut, pollingError, retryError }: { job: ReportJob; timedOut: boolean; pollingError?: string; retryError?: string }) {
  if (timedOut) return <p className={styles.timeoutMessage}>Формирование отчёта занимает слишком много времени. Попробуйте уменьшить период или количество выбранных фильтров.</p>;
  if (job.status === 'failed') return <p className={styles.jobError}>{job.error ?? 'Не удалось сформировать отчёт.'}</p>;
  if (retryError) return <p className={styles.jobActionError} role="alert">{retryError}</p>;
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
    } finally { setDownloading(false); }
  };
  if (job.status === 'ready') {
    if (job.downloadUrl?.startsWith('data:')) return <a className={styles.actionLink} href={job.downloadUrl} download={`${job.name}.${job.format}`} aria-label={`Скачать ${job.name}`}><CloudDownload size={16} fill="currentColor" />Скачать</a>;
    if (job.downloadUrl) return <><Button variant="ghost" size="s" type="button" loading={downloading} onClick={() => void download()}><CloudDownload size={16} fill="currentColor" />Скачать</Button>{downloadError ? <span role="alert" className={styles.jobActionError}>{downloadError}</span> : null}</>;
    return <span className={styles.actionUnavailable} title="Сервер не вернул download_url">Файл недоступен</span>;
  }
  if ((job.status === 'failed' || timedOut) && REPORTS_API_CAPABILITIES.retry && job.request) {
    return <Button variant="ghost" size="s" type="button" onClick={() => onRetry(job)} loading={retrying} disabled={retrying} aria-label={`Повторить ${job.name}`}>{retrying ? null : <RefreshSmall size={16} fill="currentColor" />}Повторить</Button>;
  }
  return null;
}

type JobViewProps = {
  job: ReportJob;
  pollingError?: string;
  retryError?: string;
  retrying: boolean;
  onRetry: (job: ReportJob) => void;
};

function ReportJobRow({ job, pollingError, retryError, retrying, onRetry }: JobViewProps) {
  const timedOut = hasTimedOut(job);
  const visibleStatus = timedOut ? 'failed' : job.status;
  const details = <JobStateDetails job={job} timedOut={timedOut} pollingError={pollingError} retryError={retryError} />;
  return <tr data-testid={`report-job-${job.id}`}>
    <td><strong>{job.name}</strong>{details}</td>
    <td>{job.format.toUpperCase()}</td>
    <td><JobStatus status={visibleStatus} />{job.error && job.status === 'failed' ? <Tooltip content={<span>{job.error}</span>}><span className={styles.errorHint} tabIndex={0}>Подробнее</span></Tooltip> : null}</td>
    <td><JobProgress job={job} timedOut={timedOut} /></td>
    <td><time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time></td>
    <td><div className={styles.jobActions}><JobActions job={job} timedOut={timedOut} retrying={retrying} onRetry={onRetry} /></div></td>
  </tr>;
}

function ReportJobCard({ job, pollingError, retryError, retrying, onRetry }: JobViewProps) {
  const timedOut = hasTimedOut(job);
  const visibleStatus = timedOut ? 'failed' : job.status;
  return <article className={styles.jobCard}>
    <div className={styles.jobCardHeader}><strong>{job.name}</strong><JobStatus status={visibleStatus} /></div>
    <dl>
      <div><dt>Формат</dt><dd>{job.format.toUpperCase()}</dd></div>
      <div><dt>Создан</dt><dd><time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time></dd></div>
      <div><dt>Прогресс</dt><dd><JobProgress job={job} timedOut={timedOut} /></dd></div>
    </dl>
    <JobStateDetails job={job} timedOut={timedOut} pollingError={pollingError} retryError={retryError} />
    <div className={styles.jobCardActions}><JobActions job={job} timedOut={timedOut} retrying={retrying} onRetry={onRetry} /></div>
  </article>;
}

function JobsPanel({ jobs, loading, error, pollingErrors, retryErrors, retryingId, onRetry, onRefresh }: { jobs: ReportJob[]; loading: boolean; error: unknown; pollingErrors: ReadonlyMap<string, string>; retryErrors: ReadonlyMap<string, string>; retryingId: string | null; onRetry: (job: ReportJob) => void; onRefresh: () => void }) {
  if (loading) return <TableSkeleton rows={4} columns={6} label="Загрузка задач отчётов" />;
  if (error) {
    const normalized = normalizeApiError(error, { fallbackMessage: 'Не удалось загрузить задачи отчётов.' });
    return <ErrorState title={normalized.message} description="Попробуйте повторить запрос." headingLevel={3} onRetry={onRefresh} />;
  }
  if (!jobs.length) return <EmptyState title="Отчёты ещё не формировались" description="Созданные задачи появятся здесь." headingLevel={3} />;
  return <TableShell ariaLabel="Задачи отчётов"><div className={styles.jobsDesktop}><table><caption className={styles.visuallyHidden}>Задачи отчётов</caption><thead><tr><th scope="col">Отчёт</th><th scope="col">Формат</th><th scope="col">Статус</th><th scope="col">Прогресс</th><th scope="col">Создан</th><th scope="col">Действия</th></tr></thead><tbody>{jobs.map((job) => <ReportJobRow key={job.id} job={job} pollingError={pollingErrors.get(job.id)} retryError={retryErrors.get(job.id)} retrying={retryingId === job.id} onRetry={onRetry} />)}</tbody></table></div><div className={styles.jobsMobile}>{jobs.map((job) => <ReportJobCard key={job.id} job={job} pollingError={pollingErrors.get(job.id)} retryError={retryErrors.get(job.id)} retrying={retryingId === job.id} onRetry={onRetry} />)}</div></TableShell>;
}

function ColumnSelector({ control, errors }: { control: ReturnType<typeof useForm<ReportFormSchema>>['control']; errors: ReturnType<typeof useForm<ReportFormSchema>>['formState']['errors'] }) {
  return <div className={styles.columnSection}><div className={styles.sectionHeading}><div><h3>Колонки</h3><p>Выберите данные, которые войдут в отчёт.</p></div><span>{errors.columnIds?.message ? <FormError id="report-columns-error">{String(errors.columnIds.message)}</FormError> : null}</span></div><Controller control={control} name="columnIds" render={({ field }) => <><div className={styles.columnPresets} aria-label="Наборы колонок">{reportColumnPresetNames.map((name) => <Button key={name} variant="ghost" size="s" type="button" onClick={() => field.onChange(reportColumnPresets[name])}>{name}</Button>)}</div><div className={styles.columnGrid}>{reportColumnDefinitions.map((column) => <label key={column.id}><input type="checkbox" checked={field.value.includes(column.id)} onChange={(event) => field.onChange(event.target.checked ? [...field.value, column.id] : field.value.filter((value) => value !== column.id))} /><span>{column.label}</span></label>)}</div></>} /></div>;
}

function ReportForm({ onCreated }: { onCreated: (job: ReportJob) => void }) {
  const filtersQuery = useQuery({ queryKey: reportQueryKeys.filterOptions, queryFn: getReportFilterOptions, staleTime: 5 * 60_000 });
  const availableFilters = filtersQuery.data ?? reportFilterOptions;
  const [notification, setNotification] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const { control, handleSubmit, setValue, setError, setFocus, formState: { errors }, clearErrors } = useForm<ReportFormSchema>({ resolver: zodResolver(reportSchema), mode: 'onBlur', defaultValues: EMPTY_REPORT_FORM });
  const values = useWatch({ control }) as ReportFormSchema;
  const createMutation = useMutation({ mutationFn: (input: ReportFormSchema) => createReportJob(reportRequestFromForm(input)), onSuccess: (job) => { setGlobalError(null); setNotification({ intent: 'success', title: 'Задача отчёта создана', message: 'Задача добавлена в список и будет обновляться автоматически.' }); onCreated(job); }, onError: (cause) => { const normalized = normalizeApiError(cause, { fallbackMessage: 'Не удалось создать задачу отчёта.' }); const mapped = applyServerErrorsToForm(normalized, { fields: reportFields, setError, setFocus }); setGlobalError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : null); setNotification({ intent: 'error', title: 'Отчёт не создан', message: normalized.message }); } });
  const setPeriod = (dateFrom: string, dateTo: string) => { setValue('dateFrom', dateFrom, { shouldDirty: true, shouldValidate: true }); setValue('dateTo', dateTo, { shouldDirty: true, shouldValidate: true }); clearErrors(['dateFrom', 'dateTo']); };
  const clearFilters = () => {
    setPeriod('', '');
    setValue('universityIds', []); setValue('directionIds', []); setValue('productIds', []); setValue('responsibleIds', []); setValue('workflowStatuses', []);
  };
  const activeFilters: ActiveFilterItem[] = [
    ...(values.dateFrom || values.dateTo ? [{ id: 'period', label: `Период: ${values.dateFrom || '…'} — ${values.dateTo || '…'}`, onRemove: () => setPeriod('', '') }] : []),
    ...([['universityIds', 'ВУЗы', availableFilters.universities], ['directionIds', 'Направления', availableFilters.directions], ['productIds', 'Продукты', availableFilters.products], ['responsibleIds', 'ФИО', availableFilters.responsibles], ['workflowStatuses', 'Статусы Workflow', availableFilters.workflowStatuses]] as const)
      .filter(([key]) => values[key].length)
      .map(([key, label, entries]) => ({ id: key, label: `${label}: ${values[key].map((id) => entries.find((entry) => entry.id === id)?.name ?? id).join(', ')}`, onRemove: () => setValue(key, [], { shouldDirty: true }) })),
  ];
  const submit = (input: ReportFormSchema) => { setGlobalError(null); if (!REPORTS_API_CAPABILITIES.formats[input.format]) { setGlobalError(`Формат ${input.format.toUpperCase()} пока недоступен.`); return; } if (!REPORTS_API_CAPABILITIES.filters && (input.dateFrom || input.dateTo || input.universityIds.length || input.directionIds.length || input.productIds.length || input.responsibleIds.length || input.workflowStatuses.length)) { setGlobalError('Фильтры для этого отчёта пока недоступны. Выберите формат и колонки.'); return; } createMutation.mutate(input); };

  return <div className={styles.formSurface}>
    <div className={styles.sectionHeading}><div><h2>Параметры отчёта</h2></div><Filter size={20} fill="currentColor" aria-hidden="true" /></div>
    {globalError ? <FormErrorBanner>{globalError}</FormErrorBanner> : null}
    <form onSubmit={(event) => void handleSubmit(submit)(event)} noValidate>
      <section className={styles.formSection}><FilterToolbar embedded label="Фильтры отчёта" activeFilters={activeFilters} controls={() => <><DateRangeField presets from={values.dateFrom} to={values.dateTo} onFromChange={(dateFrom) => setPeriod(dateFrom, values.dateTo)} onToChange={(dateTo) => setPeriod(values.dateFrom, dateTo)} onRangeChange={setPeriod} fromError={errors.dateFrom?.message} toError={errors.dateTo?.message} /><Controller control={control} name="universityIds" render={({ field }) => <MultiSelect label="ВУЗы" searchable options={availableFilters.universities} disabled={filtersQuery.isPending || filtersQuery.isError} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="directionIds" render={({ field }) => <MultiSelect label="Направления" options={availableFilters.directions} disabled={filtersQuery.isPending || filtersQuery.isError} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="productIds" render={({ field }) => <MultiSelect label="Продукты" options={availableFilters.products} disabled={filtersQuery.isPending || filtersQuery.isError} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="responsibleIds" render={({ field }) => <MultiSelect label="ФИО" searchable options={availableFilters.responsibles} disabled={filtersQuery.isPending || filtersQuery.isError} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="workflowStatuses" render={({ field }) => <MultiSelect label="Статусы Workflow" options={availableFilters.workflowStatuses} values={field.value} onChange={field.onChange} />} /></>} onReset={clearFilters} resetDisabled={!activeFilters.length} mobileCount={activeFilters.length} />{filtersQuery.isError ? <FormErrorBanner>Не удалось загрузить справочники. <Button type="button" variant="ghost" size="s" onClick={() => void filtersQuery.refetch()}>Повторить</Button></FormErrorBanner> : null}</section>
      <ColumnSelector control={control} errors={errors} />
      <section className={styles.formSection} aria-labelledby="report-format-heading"><div className={styles.sectionHeading}><div><h3 id="report-format-heading">Формат</h3><p>Выберите формат файла отчёта.</p></div></div><Controller control={control} name="format" render={({ field }) => <fieldset className={styles.radioGroup}><legend className={styles.visuallyHidden}>Формат отчёта</legend>{REPORT_FORMATS.map((format) => <label key={format.id} className={!REPORTS_API_CAPABILITIES.formats[format.id] ? styles.optionDisabled : undefined}><input type="radio" value={format.id} checked={field.value === format.id} disabled={!REPORTS_API_CAPABILITIES.formats[format.id]} onChange={() => field.onChange(format.id)} />{format.label}{!REPORTS_API_CAPABILITIES.formats[format.id] ? <small>недоступно</small> : null}</label>)}</fieldset>} /></section>
      <div className={styles.formActions}><Button type="submit" variant="primary" size="m" loading={createMutation.isPending} disabled={createMutation.isPending}>Сформировать отчёт</Button><span className={styles.actionHint}>Задача добавляется в очередь формирования без перезагрузки страницы; значения формы сохраняются при ошибке.</span></div>
    </form>
    {notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </div>;
}

function JobsSection() {
  const queryClient = useQueryClient();
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [retryErrors, setRetryErrors] = useState<Map<string, string>>(new Map());
  const jobsQuery = useQuery({ queryKey: reportQueryKeys.jobs, queryFn: listReportJobs, placeholderData: keepPreviousData, staleTime: Infinity });
  const baseJobs = jobsQuery.data ?? [];
  const addJob = useCallback((job: ReportJob) => {
    queryClient.setQueryData<ReportJob[]>(reportQueryKeys.jobs, (current = []) => [job, ...current.filter((item) => item.id !== job.id)]);
    queryClient.setQueryData(reportQueryKeys.job(job.id), job);
  }, [queryClient]);
  const activeJobs = baseJobs.filter((job) => isActiveJob(job) && !hasTimedOut(job));
  const statusQueries = useQueries({ queries: activeJobs.map((job) => ({
    queryKey: reportQueryKeys.job(job.id),
    queryFn: async () => {
      const next = await getReportJob(job.id);
      queryClient.setQueryData<ReportJob[]>(reportQueryKeys.jobs, (current = []) => current.map((item) => item.id === next.id ? { ...next, request: item.request ?? next.request } : item));
      return next;
    },
    enabled: REPORTS_API_CAPABILITIES.jobStatus,
    retry: 3,
    retryDelay: (attemptIndex: number) => Math.min(1_000 * 2 ** attemptIndex, 8_000),
    refetchInterval: (query: { state: { data?: ReportJob } }) => {
      const current = query.state.data;
      return !current || (isActiveJob(current) && !hasTimedOut(current)) ? 3_000 : false;
    },
  })) });
  const statusById = new Map(statusQueries.flatMap((query) => query.data ? [[query.data.id, query.data] as const] : []));
  const jobs = baseJobs.map((job) => {
    const current = statusById.get(job.id);
    return current ? { ...current, request: job.request ?? current.request } : job;
  });
  const pollingErrors = new Map<string, string>(statusQueries.flatMap((query, index) => query.error ? [[activeJobs[index].id, normalizeApiError(query.error, { fallbackMessage: 'Не удалось обновить статус отчёта.' }).message] as const] : []));
  const onRetry = async (job: ReportJob) => {
    if (retryingId || !job.request) return;
    setRetryingId(job.id);
    setRetryErrors((current) => { const next = new Map(current); next.delete(job.id); return next; });
    try {
      addJob(await retryReportJob(job));
    } catch (cause) {
      setRetryErrors((current) => new Map(current).set(job.id, normalizeApiError(cause, { fallbackMessage: 'Не удалось повторить формирование отчёта.' }).message));
    } finally {
      setRetryingId(null);
    }
  };
  return <div className={styles.reportsLayout}><ReportForm onCreated={addJob} /><section className={styles.jobsSurface} aria-labelledby="report-jobs-heading"><div className={styles.jobsHeader}><div><p className={styles.eyebrow}>Очередь формирования</p><h2 id="report-jobs-heading">Задачи отчётов</h2><p>В очереди и во время формирования статус обновляется примерно каждые 3 секунды.</p></div><span className={styles.jobsCapability}><InformationStroke size={16} fill="currentColor" aria-hidden="true" />История задач загружается с сервера.</span></div><JobsPanel jobs={jobs} loading={jobsQuery.isPending} error={jobsQuery.data ? null : jobsQuery.error} pollingErrors={pollingErrors} retryErrors={retryErrors} retryingId={retryingId} onRetry={onRetry} onRefresh={() => void jobsQuery.refetch()} /></section></div>;
}

export function ReportsPage() {
  return <div className={styles.page}><JobsSection /></div>;
}
