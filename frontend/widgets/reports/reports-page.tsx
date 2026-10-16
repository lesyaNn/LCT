'use client';

import Filter from '@atomaro/icons/24/action/Filter';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import FolderAdd from '@atomaro/icons/24/document/FolderAdd';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useDebouncedValue } from './use-debounced-value';
import { useForm, useWatch } from 'react-hook-form';
import { applyServerErrorsToForm, normalizeApiError } from '@/shared/lib/api-errors';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import {
  EMPTY_REPORT_FORM,
  REPORTS_API_CAPABILITIES,
  createReportJob,
  getReportJob,
  getReportPreview,
  getReportStatistics,
  listReportJobs,
  reportFormFromTemplate,
  reportQueryKeys,
  reportRequestFromForm,
  retryReportJob,
  type ReportJob,
  type ReportJobStatus,
  type ReportTemplate,
} from '@/shared/lib/reports-repository';
import { reportFields, reportSchema, type ReportFormSchema } from './report-form-schema';
import { buildActiveFilters, ReportFilterFields } from './report-filters';
import { ReportColumnSelector } from './report-columns';
import { ReportFormatField } from './report-format';
import { ReportPreviewTable } from './report-preview';
import { ReportStatisticsPanel } from './report-statistics';
import { ReportTemplatesSection } from './report-templates';
import { ReportJobsPanel, isActiveJob } from './report-jobs';
import styles from './reports-page.module.css';

type Notification = { intent: ToastIntent; title: string; message?: string; key?: number };

/* ------------------------------------------------------------- parameters */

function ReportParameters({ onCreated }: { onCreated: (job: ReportJob) => void }) {
  const [notification, setNotification] = useState<Notification | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const { control, handleSubmit, setValue, setError, setFocus, formState: { errors, isDirty }, clearErrors } = useForm<ReportFormSchema>({
    resolver: zodResolver(reportSchema),
    mode: 'onBlur',
    defaultValues: EMPTY_REPORT_FORM,
  });
  const values = useWatch({ control }) as ReportFormSchema;

  const createMutation = useMutation({
    mutationFn: (input: ReportFormSchema) => createReportJob(reportRequestFromForm(input)),
    onSuccess: (job) => {
      setGlobalError(null);
      setNotification({ intent: 'success', title: 'Задача отчёта создана', message: 'Отчёт появится в очереди и будет обновляться автоматически.' });
      onCreated(job);
    },
    onError: (cause) => {
      const normalized = normalizeApiError(cause, { fallbackMessage: 'Не удалось создать задачу отчёта.' });
      const mapped = applyServerErrorsToForm(normalized, { fields: reportFields, setError, setFocus });
      setGlobalError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : null);
      setNotification({ intent: 'error', title: 'Отчёт не создан', message: normalized.message });
    },
  });

  // Live preview + statistics of the current selection (ТЗ steps 8 and the
  // "same selection" rule). Debounced so typing a date does not fire a
  // request per keystroke, and the previous data stays visible meanwhile.
  const request = reportRequestFromForm(values);
  const debouncedRequest = useDebouncedValue(request);
  const selectionKey = JSON.stringify(debouncedRequest);

  // Always on: the report covers the whole registry, so there is nothing to
  // wait for and the page opens with a real preview.
  const previewQuery = useQuery({
    queryKey: [...reportQueryKeys.preview, selectionKey],
    queryFn: () => getReportPreview(debouncedRequest),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const statisticsQuery = useQuery({
    queryKey: [...reportQueryKeys.statistics, selectionKey],
    queryFn: () => getReportStatistics(debouncedRequest),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  const setPeriod = (dateFrom: string, dateTo: string) => {
    setValue('dateFrom', dateFrom, { shouldDirty: true, shouldValidate: true });
    setValue('dateTo', dateTo, { shouldDirty: true, shouldValidate: true });
    clearErrors(['dateFrom', 'dateTo']);
  };
  const clearFilters = () => setPeriod('', '');

  const activeFilters = buildActiveFilters(values, setPeriod);

  const submit = (input: ReportFormSchema) => {
    setGlobalError(null);
    if (!REPORTS_API_CAPABILITIES.formats[input.format]) {
      setGlobalError(`Формат ${input.format.toUpperCase()} пока недоступен.`);
      return;
    }
    createMutation.mutate(input);
  };

  return (
    <div className={styles.reportsLayout}>
      <section className={styles.periodSurface} aria-labelledby="report-period-heading">
        <div className={styles.sectionHeading}>
          <div className={styles.headingWithIcon}>
            <Calendar size={18} fill="currentColor" aria-hidden="true" />
            <div>
              <h3 id="report-period-heading">Период</h3>
              <p>Выберите готовый период или укажите даты.</p>
            </div>
          </div>
        </div>
        <ReportFilterFields
          values={values}
          errors={errors}
          onPeriodChange={setPeriod}
          onReset={clearFilters}
          activeFilters={activeFilters}
        />
      </section>
      <div className={styles.formSurface}>
        <div className={styles.sectionHeading}>
          <div className={styles.headingWithIcon}>
            <Filter size={20} fill="currentColor" aria-hidden="true" />
            <h2>Параметры отчёта</h2>
          </div>
        </div>
        {globalError ? <FormErrorBanner>{globalError}</FormErrorBanner> : null}
        <form onSubmit={(event) => void handleSubmit(submit)(event)} noValidate>
          <ReportColumnSelector control={control} error={errors.columnIds?.message} />
          <ReportFormatField control={control} />
          <div className={styles.formActions}>
            <Button type="submit" variant="primary" size="m" loading={createMutation.isPending} disabled={createMutation.isPending}>
              Сформировать отчёт
            </Button>
            <Button type="button" variant="secondary" size="m" onClick={() => setSaveTemplateOpen(true)}>
              <FolderAdd size={16} fill="currentColor" aria-hidden="true" />Сохранить как шаблон
            </Button>
            <span className={styles.actionHint}>
              Отчёт формируется в фоне; значения формы сохраняются при ошибке.
            </span>
          </div>
        </form>
      </div>
      <div className={styles.sideColumn}>
        <div className={styles.sideScroll}>
          <ReportQueue />
          <ReportTemplatesSection
            currentValues={values}
            saveOpen={saveTemplateOpen}
            onCloseSave={() => setSaveTemplateOpen(false)}
            onApply={(template: ReportTemplate) => {
              const next = reportFormFromTemplate(template);
              (Object.keys(next) as Array<keyof typeof next>).forEach((key) =>
                setValue(key, next[key] as never, { shouldDirty: true, shouldValidate: true }),
              );
              setNotification({ intent: 'success', title: 'Шаблон применён', message: template.name });
            }}
          />
        </div>
      </div>
      <div className={styles.resultCard}>
        <ReportPreviewTable
          preview={previewQuery.data}
          pending={previewQuery.isPending || previewQuery.isFetching}
          error={previewQuery.isError ? previewQuery.error : null}
          dirty={isDirty}
          onRetry={() => void previewQuery.refetch()}
        />
      </div>
      <div className={styles.resultCard}>
        <ReportStatisticsPanel
          statistics={statisticsQuery.data}
          pending={statisticsQuery.isPending || statisticsQuery.isFetching}
          error={statisticsQuery.isError ? statisticsQuery.error : null}
          dirty
          onRetry={() => void statisticsQuery.refetch()}
        />
      </div>
      {notification ? (
        <div className={styles.toastViewport}>
          <Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} />
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ jobs */

function ReportQueue() {
  const queryClient = useQueryClient();
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [retryErrors, setRetryErrors] = useState<Map<string, string>>(new Map());
  const [feed, setFeed] = useState<Notification | null>(null);

  const jobsQuery = useQuery({
    queryKey: reportQueryKeys.jobs,
    queryFn: listReportJobs,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
  const baseJobs = jobsQuery.data ?? [];

  const addJob = useCallback((job: ReportJob) => {
    queryClient.setQueryData<ReportJob[]>(reportQueryKeys.jobs, (current = []) => [job, ...current.filter((item) => item.id !== job.id)]);
    queryClient.setQueryData(reportQueryKeys.job(job.id), job);
  }, [queryClient]);

  const activeJobs = baseJobs.filter((job) => isActiveJob(job));
  const prevStatuses = useRef(new Map<string, ReportJobStatus>());
  const statusQueries = useQueries({
    queries: activeJobs.map((job) => ({
      queryKey: reportQueryKeys.job(job.id),
      queryFn: async () => {
        const next = await getReportJob(job.id);
        queryClient.setQueryData<ReportJob[]>(reportQueryKeys.jobs, (current = []) =>
          current.map((item) => item.id === next.id ? { ...next, request: item.request ?? next.request } : item),
        );
        return next;
      },
      enabled: REPORTS_API_CAPABILITIES.jobStatus,
      retry: 3,
      retryDelay: (attemptIndex: number) => Math.min(1_000 * 2 ** attemptIndex, 8_000),
      refetchInterval: (query: { state: { data?: ReportJob } }) => {
        const current = query.state.data;
        return !current || isActiveJob(current) ? 3_000 : false;
      },
    })),
  });

  const statusById = new Map(statusQueries.flatMap((query) => query.data ? [[query.data.id, query.data] as const] : []));
  const jobs = baseJobs.map((job) => {
    const current = statusById.get(job.id);
    return current ? { ...current, request: job.request ?? current.request } : job;
  });

  useEffect(() => {
    for (const job of jobs) {
      const prev = prevStatuses.current.get(job.id);
      if (prev && isActiveJob({ ...job, status: prev }) && !isActiveJob(job)) {
        setFeed(
          job.status === 'ready'
            ? { intent: 'success', title: 'Отчёт готов', message: `${job.name} можно скачать.`, key: Date.now() }
            : { intent: 'error', title: 'Не удалось сформировать отчёт', message: job.error ?? job.name, key: Date.now() },
        );
      }
      prevStatuses.current.set(job.id, job.status);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.map((job) => `${job.id}:${job.status}`).join(',')]);

  const pollingErrors = new Map<string, string>(
    statusQueries.flatMap((query, index) => query.error
      ? [[activeJobs[index].id, normalizeApiError(query.error, { fallbackMessage: 'Не удалось обновить статус отчёта.' }).message] as const]
      : []),
  );

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

  return (
    <section className={styles.jobsSurface} aria-labelledby="report-jobs-heading" tabIndex={0}>
      <div className={styles.jobsHeader}>
        <DocumentText size={20} fill="currentColor" aria-hidden="true" />
        <div>
          <h2 id="report-jobs-heading">Сформированные отчёты</h2>
          <p>В очереди и во время формирования статус обновляется примерно каждые 3 секунды.</p>
        </div>
      </div>
      <ReportJobsPanel
        jobs={jobs}
        loading={jobsQuery.isPending}
        error={jobsQuery.data ? null : jobsQuery.error}
        pollingErrors={pollingErrors}
        retryErrors={retryErrors}
        retryingId={retryingId}
        onRetry={onRetry}
        onRefresh={() => void jobsQuery.refetch()}
      />
      {feed ? (
        <div className={styles.toastViewport}>
          <Toast key={feed.key} intent={feed.intent} title={feed.title} message={feed.message} onClose={() => setFeed(null)} />
        </div>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ page */

export function ReportsPage() {
  const queryClient = useQueryClient();

  return (
    <div className={styles.page}>
      <ReportParameters
        onCreated={(job) => {
          queryClient.setQueryData<ReportJob[]>(reportQueryKeys.jobs, (current = []) => [job, ...current.filter((item) => item.id !== job.id)]);
        }}
      />
    </div>
  );
}

export { REPORT_JOB_TIMEOUT_MS } from './report-jobs';
