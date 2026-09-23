'use client';

import Calendar from '@atomaro/icons/24/communication/Calendar';
import CloudDownload from '@atomaro/icons/24/action/CloudDownload';
import Filter from '@atomaro/icons/24/action/Filter';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import RefreshSmall from '@atomaro/icons/24/action/RefreshSmall';
import { zodResolver } from '@hookform/resolvers/zod';
import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';
import { applyServerErrorsToForm, normalizeApiError } from '@/shared/lib/api-errors';
import { formatDateTimeRu } from '@/shared/lib/formatters';
import { Button } from '@/shared/ui/rtk/button';
import { FormError, FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Input } from '@/shared/ui/rtk/form-controls';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { Progress } from '@/shared/ui/rtk/progress';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import {
  EMPTY_REPORT_FORM,
  REPORTS_API_CAPABILITIES,
  REPORT_FORMATS,
  createReportJob,
  getReportJob,
  listReportJobs,
  reportColumnDefinitions,
  reportColumnPresetNames,
  reportFilterOptions,
  reportPeriodPreset,
  reportQueryKeys,
  reportRequestFromForm,
  type ReportFormValues,
  type ReportJob,
  type ReportJobStatus,
  type ReportPeriodPreset,
} from '@/shared/lib/reports-repository';
import styles from './reports-page.module.css';

const reportFields = ['dateFrom', 'dateTo', 'universityIds', 'directionIds', 'productIds', 'responsibleIds', 'workflowStatuses', 'columnIds', 'format'] as const;

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

const periodPresets: Array<{ id: Exclude<ReportPeriodPreset, null>; label: string }> = [
  { id: 'current_month', label: 'Текущий месяц' },
  { id: 'current_quarter', label: 'Текущий квартал' },
  { id: 'current_year', label: 'Текущий год' },
  { id: 'previous_year', label: 'Прошлый год' },
];

const statusMeta: Record<ReportJobStatus, { label: string; intent: 'neutral' | 'brand' | 'success' | 'danger' }> = {
  queued: { label: 'В очереди', intent: 'neutral' },
  building: { label: 'Формируется', intent: 'brand' },
  ready: { label: 'Готов', intent: 'success' },
  failed: { label: 'Ошибка', intent: 'danger' },
};

function activePreset(values: Pick<ReportFormValues, 'dateFrom' | 'dateTo'>): ReportPeriodPreset {
  return periodPresets.find((preset) => {
    const dates = reportPeriodPreset(preset.id);
    return dates.dateFrom === values.dateFrom && dates.dateTo === values.dateTo;
  })?.id ?? null;
}

function JobStatus({ status }: { status: ReportJobStatus }) {
  const meta = statusMeta[status];
  return <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>;
}

function ReportJobRow({ job }: { job: ReportJob }) {
  const canDownload = Boolean(REPORTS_API_CAPABILITIES.download && job.downloadUrl);
  return <tr>
    <td><strong>{job.name}</strong></td>
    <td>{job.format.toUpperCase()}</td>
    <td><JobStatus status={job.status} />{job.error ? <Tooltip content={<span>{job.error}</span>}><span className={styles.errorHint} tabIndex={0}>Подробнее</span></Tooltip> : null}</td>
    <td>{job.status === 'building' ? job.progress !== null ? <div className={styles.progressCell}><Progress value={job.progress} label={`Прогресс отчёта ${job.name}`} /><span>{job.progress}%</span></div> : <span className={styles.muted}>Статус обновляется…</span> : <span className={styles.muted}>—</span>}</td>
    <td><time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time></td>
    <td><div className={styles.jobActions}>{job.status === 'ready' ? canDownload ? <a className={styles.actionLink} href={job.downloadUrl} download><CloudDownload size={16} fill="currentColor" />Скачать</a> : <Button variant="ghost" size="s" type="button" disabled title="Download endpoint отсутствует в текущем Reports API"><CloudDownload size={16} fill="currentColor" />Скачать</Button> : null}{job.status === 'failed' ? <Button variant="ghost" size="s" type="button" disabled={!REPORTS_API_CAPABILITIES.retry} title="Retry endpoint отсутствует в текущем Reports API"><RefreshSmall size={16} fill="currentColor" />Повторить</Button> : null}</div></td>
  </tr>;
}

function ReportJobCard({ job }: { job: ReportJob }) {
  return <article className={styles.jobCard}><div className={styles.jobCardHeader}><strong>{job.name}</strong><JobStatus status={job.status} /></div><dl><div><dt>Формат</dt><dd>{job.format.toUpperCase()}</dd></div><div><dt>Создан</dt><dd><time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time></dd></div><div><dt>Прогресс</dt><dd>{job.status === 'building' ? job.progress !== null ? `${job.progress}%` : 'Статус обновляется…' : '—'}</dd></div></dl>{job.error ? <p className={styles.jobError}>{job.error}</p> : null}<div className={styles.jobCardActions}>{job.status === 'ready' ? <Button variant="secondary" size="s" type="button" disabled title="Download endpoint отсутствует в текущем Reports API"><CloudDownload size={16} fill="currentColor" />Скачать</Button> : null}{job.status === 'failed' ? <Button variant="ghost" size="s" type="button" disabled={!REPORTS_API_CAPABILITIES.retry} title="Retry endpoint отсутствует в текущем Reports API"><RefreshSmall size={16} fill="currentColor" />Повторить</Button> : null}</div></article>;
}

function JobsPanel({ jobs, loading, error, onRetry }: { jobs: ReportJob[]; loading: boolean; error: unknown; onRetry: () => void }) {
  if (loading) return <TableShell ariaLabel="Загрузка задач отчётов" ariaBusy><div className={styles.jobsSkeleton}>{Array.from({ length: 4 }, (_, index) => <div key={index}><span /><span /><span /><span /></div>)}</div></TableShell>;
  if (error) {
    const normalized = normalizeApiError(error, { fallbackMessage: 'Не удалось загрузить задачи отчётов.' });
    return <div className={styles.jobsError} role="alert"><h3>{normalized.message}</h3><Button variant="secondary" size="s" type="button" onClick={onRetry}>Повторить</Button></div>;
  }
  if (!jobs.length) return <div className={styles.jobsEmpty} role="status"><h3>Отчёты ещё не формировались</h3><p>Созданные в этой сессии задачи появятся здесь.</p><p className={styles.apiNote}>В текущем Reports API нет endpoint списка jobs, поэтому история задач пока недоступна.</p></div>;
  return <TableShell ariaLabel="Задачи отчётов"><div className={styles.jobsDesktop}><table><caption className={styles.visuallyHidden}>Задачи отчётов</caption><thead><tr><th scope="col">Отчёт</th><th scope="col">Формат</th><th scope="col">Статус</th><th scope="col">Прогресс</th><th scope="col">Создан</th><th scope="col">Действия</th></tr></thead><tbody>{jobs.map((job) => <ReportJobRow key={job.id} job={job} />)}</tbody></table></div><div className={styles.jobsMobile}>{jobs.map((job) => <ReportJobCard key={job.id} job={job} />)}</div></TableShell>;
}

function ColumnSelector({ control, errors }: { control: ReturnType<typeof useForm<ReportFormSchema>>['control']; errors: ReturnType<typeof useForm<ReportFormSchema>>['formState']['errors'] }) {
  return <div className={styles.columnSection}><div className={styles.sectionHeading}><div><h3>Колонки</h3><p>Идентификаторы отделены от отображаемых названий.</p></div><span>{errors.columnIds?.message ? <FormError id="report-columns-error">{String(errors.columnIds.message)}</FormError> : null}</span></div><Controller control={control} name="columnIds" render={({ field }) => <><div className={styles.columnPresets} aria-label="Наборы колонок">{reportColumnPresetNames.map((name) => <Button key={name} variant="ghost" size="s" type="button" disabled title="Точный состав набора будет предоставлен P4-02-01">{name}</Button>)}</div><div className={styles.columnGrid}>{reportColumnDefinitions.map((column) => <label key={column.id}><input type="checkbox" checked={field.value.includes(column.id)} onChange={(event) => field.onChange(event.target.checked ? [...field.value, column.id] : field.value.filter((value) => value !== column.id))} /><span>{column.label}</span></label>)}</div></>} /></div>;
}

function ReportForm({ onCreated }: { onCreated: (job: ReportJob) => void }) {
  const [notification, setNotification] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const { control, handleSubmit, setValue, setError, setFocus, formState: { errors }, clearErrors } = useForm<ReportFormSchema>({ resolver: zodResolver(reportSchema), mode: 'onBlur', defaultValues: EMPTY_REPORT_FORM });
  const values = useWatch({ control }) as ReportFormSchema;
  const preset = activePreset(values);
  const createMutation = useMutation({ mutationFn: (input: ReportFormSchema) => createReportJob(reportRequestFromForm(input)), onSuccess: (job) => { setGlobalError(null); setNotification({ intent: 'success', title: 'Задача отчёта создана', message: 'Задача добавлена в список и будет обновляться автоматически.' }); onCreated(job); }, onError: (cause) => { const normalized = normalizeApiError(cause, { fallbackMessage: 'Не удалось создать задачу отчёта.' }); const mapped = applyServerErrorsToForm(normalized, { fields: reportFields, setError, setFocus }); setGlobalError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : null); setNotification({ intent: 'error', title: 'Отчёт не создан', message: normalized.message }); } });
  const setPreset = (value: Exclude<ReportPeriodPreset, null>) => { const dates = reportPeriodPreset(value); setValue('dateFrom', dates.dateFrom, { shouldDirty: true, shouldValidate: true }); setValue('dateTo', dates.dateTo, { shouldDirty: true, shouldValidate: true }); clearErrors(['dateFrom', 'dateTo']); };
  const submit = (input: ReportFormSchema) => { setGlobalError(null); if (!REPORTS_API_CAPABILITIES.formats[input.format]) { setGlobalError(`Формат ${input.format.toUpperCase()} пока не поддерживается текущим Reports API.`); return; } if (!REPORTS_API_CAPABILITIES.filters && (input.dateFrom || input.dateTo || input.universityIds.length || input.directionIds.length || input.productIds.length || input.responsibleIds.length || input.workflowStatuses.length)) { setGlobalError('Текущий Reports API принимает только формат и колонки. Фильтры формы будут подключены после P4 unified filters/report contract.'); return; } createMutation.mutate(input); };

  return <div className={styles.formSurface}>
    <div className={styles.sectionHeading}><div><h2>Параметры отчёта</h2><p>Соберите конфигурацию и отправьте её в очередь формирования.</p></div><Filter size={20} fill="currentColor" aria-hidden="true" /></div>
    {globalError ? <FormErrorBanner>{globalError}</FormErrorBanner> : null}
    <form onSubmit={(event) => void handleSubmit(submit)(event)} noValidate>
      <section className={styles.formSection} aria-labelledby="report-period-heading"><div className={styles.sectionHeading}><div><h3 id="report-period-heading">Период</h3><p>Выберите готовый период или задайте даты вручную.</p></div><Calendar size={18} fill="currentColor" aria-hidden="true" /></div><div className={styles.presetRow}>{periodPresets.map((item) => <Button key={item.id} type="button" variant={preset === item.id ? 'primary' : 'ghost'} size="s" onClick={() => setPreset(item.id)}>{item.label}</Button>)}</div><div className={styles.dateGrid}><FormField label="С даты" htmlFor="report-date-from" error={errors.dateFrom?.message} errorId="report-date-from-error"><Input id="report-date-from" type="date" aria-invalid={Boolean(errors.dateFrom)} aria-describedby={errors.dateFrom ? 'report-date-from-error' : undefined} {...({ name: 'dateFrom', value: values.dateFrom, onChange: (event) => { setValue('dateFrom', event.target.value, { shouldDirty: true, shouldValidate: true }); clearErrors('dateFrom'); }, onBlur: () => undefined })} /></FormField><FormField label="По дату" htmlFor="report-date-to" error={errors.dateTo?.message} errorId="report-date-to-error"><Input id="report-date-to" type="date" aria-invalid={Boolean(errors.dateTo)} aria-describedby={errors.dateTo ? 'report-date-to-error' : undefined} {...({ name: 'dateTo', value: values.dateTo, onChange: (event) => { setValue('dateTo', event.target.value, { shouldDirty: true, shouldValidate: true }); clearErrors('dateTo'); }, onBlur: () => undefined })} /></FormField></div></section>
      <section className={styles.formSection} aria-labelledby="report-filters-heading"><div className={styles.sectionHeading}><div><h3 id="report-filters-heading">Фильтры</h3><p>Опции берутся из общих каталогов проекта.</p></div></div><div className={styles.filterGrid}><Controller control={control} name="universityIds" render={({ field }) => <MultiSelect label="ВУЗы" searchable options={reportFilterOptions.universities} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="directionIds" render={({ field }) => <MultiSelect label="Направления" options={reportFilterOptions.directions} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="productIds" render={({ field }) => <MultiSelect label="Продукты" options={reportFilterOptions.products} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="responsibleIds" render={({ field }) => <MultiSelect label="ФИО" searchable options={reportFilterOptions.responsibles} values={field.value} onChange={field.onChange} />} /><Controller control={control} name="workflowStatuses" render={({ field }) => <MultiSelect label="Статусы Workflow" options={reportFilterOptions.workflowStatuses} values={field.value} onChange={field.onChange} />} /></div></section>
      <ColumnSelector control={control} errors={errors} />
      <section className={styles.formSection} aria-labelledby="report-format-heading"><div className={styles.sectionHeading}><div><h3 id="report-format-heading">Формат</h3><p>Выберите формат файла отчёта.</p></div></div><Controller control={control} name="format" render={({ field }) => <fieldset className={styles.radioGroup}><legend className={styles.visuallyHidden}>Формат отчёта</legend>{REPORT_FORMATS.map((format) => <label key={format.id} className={!REPORTS_API_CAPABILITIES.formats[format.id] ? styles.optionDisabled : undefined}><input type="radio" value={format.id} checked={field.value === format.id} disabled={!REPORTS_API_CAPABILITIES.formats[format.id]} onChange={() => field.onChange(format.id)} />{format.label}{!REPORTS_API_CAPABILITIES.formats[format.id] ? <small>ожидает API</small> : null}</label>)}</fieldset>} /></section>
      <div className={styles.formActions}><Button type="submit" variant="primary" size="m" disabled={createMutation.isPending}>{createMutation.isPending ? 'Формирование…' : 'Сформировать отчёт'}</Button><span className={styles.actionHint}>Задача будет добавлена в Report Jobs без перезагрузки страницы.</span></div>
    </form>
    {notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </div>;
}

function JobsSection() {
  const queryClient = useQueryClient();
  const jobsQuery = useQuery({ queryKey: reportQueryKeys.jobs, queryFn: listReportJobs, placeholderData: keepPreviousData, staleTime: 30_000 });
  const baseJobs = jobsQuery.data ?? [];
  const activeJobs = baseJobs.filter((job) => job.status === 'queued' || job.status === 'building');
  const statusQueries = useQueries({ queries: activeJobs.map((job) => ({ queryKey: reportQueryKeys.job(job.id), queryFn: () => getReportJob(job.id), enabled: REPORTS_API_CAPABILITIES.jobStatus, refetchInterval: (query: { state: { data?: unknown } }) => { const current = query.state.data as ReportJob | undefined; return !current || current.status === 'queued' || current.status === 'building' ? 3_000 : false; } })) });
  const statusById = new Map(statusQueries.flatMap((query) => query.data ? [[query.data.id, query.data] as const] : []));
  const jobs = baseJobs.map((job) => statusById.get(job.id) ?? job);
  const addJob = (job: ReportJob) => { queryClient.setQueryData<ReportJob[]>(reportQueryKeys.jobs, (current = []) => [job, ...current.filter((item) => item.id !== job.id)]); queryClient.setQueryData(reportQueryKeys.job(job.id), job); };
  return <div className={styles.reportsLayout}><ReportForm onCreated={addJob} /><section className={styles.jobsSurface} aria-labelledby="report-jobs-heading"><div className={styles.jobsHeader}><div><p className={styles.eyebrow}>Очередь формирования</p><h2 id="report-jobs-heading">Задачи отчётов</h2><p>Статусы обновляются для незавершённых задач.</p></div><span className={styles.jobsCapability}><InformationStroke size={16} fill="currentColor" aria-hidden="true" />История jobs подключится после появления list endpoint</span></div><JobsPanel jobs={jobs} loading={jobsQuery.isPending} error={jobsQuery.error} onRetry={() => void jobsQuery.refetch()} /></section></div>;
}

export function ReportsPage() {
  return <div className={styles.page}><JobsSection /></div>;
}
