'use client';

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatDateTimeRu } from '@/shared/lib/formatters';
import { ApiRequestError, normalizeApiError } from '@/shared/lib/api-errors';
import {
  adaptImportJob,
  executeSheetImport,
  executeSheetsImport,
  getImportJob,
  importQueryKeys,
  invalidateImportedDomains,
  isImportJobActive,
  listImportJobs,
  previewImportSheet,
  sortSheetsForImport,
  uploadImportFile,
  waitForImportJob,
  type ImportJob,
  type ImportSheetPreview,
  type ImportSummary,
  type ImportUploadResponse,
} from '@/shared/lib/import-repository';
import { Button, ButtonAnchor } from '@/shared/ui/rtk/button';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { ErrorState } from '@/shared/ui/error-state';
import { FormError, FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { Select, Switch } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import tableStyles from '@/shared/ui/rtk/data-table.module.css';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import styles from './import-page.module.css';

const steps = ['Файл', 'Лист', 'Предпросмотр', 'Запуск'];

const jobStatusMeta: Record<ImportJob['status'], { label: string; intent: 'neutral' | 'info' | 'success' | 'danger' }> = {
  queued: { label: 'В очереди', intent: 'neutral' },
  processing: { label: 'Обработка', intent: 'info' },
  done: { label: 'Готово', intent: 'success' },
  failed: { label: 'Ошибка', intent: 'danger' },
};

function currentStep(upload: ImportUploadResponse | null, sheetId: string, preview: ImportSheetPreview | null, dryRunSummary: ImportSummary | null): number {
  if (!upload) return 0;
  if (!sheetId || !preview) return 1;
  if (!dryRunSummary) return 2;
  return 3;
}

interface BulkSheetResult {
  sheetId: string;
  label: string;
  summary: ImportSummary | null;
  error?: string;
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function importActionError(cause: unknown, fallbackMessage: string): string {
  if (cause instanceof ApiRequestError && cause.body && typeof cause.body === 'object' && !Array.isArray(cause.body)) {
    const detail = (cause.body as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
  }
  return normalizeApiError(cause, { fallbackMessage }).message;
}

function Summary({ summary }: { summary: ImportSummary }) {
  return <div className={styles.summary} aria-label="Итоги запуска">
    <div><strong>{summary.total_rows}</strong><span>Всего</span></div>
    <div><strong>{summary.inserted}</strong><span>Добавлено</span></div>
    <div><strong>{summary.updated}</strong><span>Обновлено</span></div>
    <div><strong>{summary.skipped}</strong><span>Пропущено</span></div>
    <div className={summary.errors.length ? styles.summaryError : ''}><strong>{summary.errors_total ?? summary.errors.length}</strong><span>Ошибок</span></div>
  </div>;
}

function StepRail({ active }: { active: number }) {
  return <ol className={styles.steps} aria-label="Этапы импорта">{steps.map((label, index) => <li className={index <= active ? styles.stepActive : ''} key={label}><span>{index + 1}</span><b>{label}</b></li>)}</ol>;
}

function FileDropzone({ onFile, loading, error }: { onFile: (file: File) => void; loading: boolean; error: string | null }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const chooseFile = (file: File | undefined) => { if (file) onFile(file); };
  const onInput = (event: ChangeEvent<HTMLInputElement>) => { chooseFile(event.target.files?.[0]); event.currentTarget.value = ''; };
  const onDrop = (event: DragEvent<HTMLLabelElement>) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0]); };
  return <div className={styles.fileBlock}>
    <label data-testid="import-dropzone" className={`${styles.dropzone} ${dragging ? styles.dropzoneDragging : ''} ${error ? styles.dropzoneError : ''}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
      <input ref={inputRef} className={styles.fileInput} type="file" accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel" onChange={onInput} disabled={loading} />
      <span className={styles.uploadIcon} aria-hidden="true">↑</span>
      <strong>{loading ? 'Читаем листы файла…' : 'Перетащите XLSX сюда или выберите файл'}</strong>
      <small>Поддерживаются .xlsx и .xls, размер до 10 МБ</small>
    </label>
    {error ? <FormError id="import-file-error">{error}</FormError> : null}
  </div>;
}

function SheetPreview({ preview, summary }: { preview: ImportSheetPreview; summary: ImportSummary | null }) {
  const errors = new Map((summary?.errors ?? []).map((item) => [`${item.row}:${item.field}`, item.error]));
  return <section className={styles.section} aria-labelledby="preview-heading">
    <div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 3</p><h2 id="preview-heading">Предпросмотр листа</h2><p>Первые {Math.min(10, preview.preview.length)} строк из {preview.row_count}.</p></div></div>
    <TableShell className={styles.previewShell} ariaLabel="Предпросмотр импорта"><div className={styles.previewDesktop}><table className={tableStyles.table} data-testid="preview-table"><caption className={styles.visuallyHidden}>Первые строки выбранного листа</caption><thead><tr><th scope="col">Строка</th>{preview.headers.map((header) => <th scope="col" key={header}>{header}</th>)}</tr></thead><tbody>{preview.preview.slice(0, 10).map((row, index) => <tr key={index}>{<td>{index + 2}</td>}{preview.headers.map((header) => { const error = errors.get(`${index + 2}:${header}`); return <td className={error ? styles.cellError : undefined} title={error} key={`${index}-${header}`}>{valueText(row[header])}</td>; })}</tr>)}</tbody></table></div><div className={styles.previewMobile}>{preview.preview.slice(0, 10).map((row, index) => <article key={index}><strong>Строка {index + 2}</strong><dl>{preview.headers.map((header) => <div key={header}><dt>{header}</dt><dd>{valueText(row[header])}</dd></div>)}</dl></article>)}</div></TableShell>
  </section>;
}

function BulkResults({ results }: { results: BulkSheetResult[] }) {
  return <TableShell ariaLabel="Итоги по листам"><div className={styles.previewDesktop}><table className={tableStyles.table} data-testid="bulk-results"><caption className={styles.visuallyHidden}>Итоги запуска по листам</caption><thead><tr><th scope="col">Лист</th><th scope="col">Всего</th><th scope="col">Добавлено</th><th scope="col">Обновлено</th><th scope="col">Ошибок</th><th scope="col">Статус</th></tr></thead><tbody>{results.map((item) => <tr key={item.sheetId}><td>{item.label}</td><td>{item.summary?.total_rows ?? '—'}</td><td>{item.summary?.inserted ?? '—'}</td><td>{item.summary?.updated ?? '—'}</td><td>{item.summary ? (item.summary.errors_total ?? item.summary.errors.length) : '—'}</td><td>{item.error ?? (item.summary ? 'Ок' : '…')}</td></tr>)}</tbody></table></div></TableShell>;
}

function OptionsAndRun({
  updateExisting,
  setUpdateExisting,
  dryRunSummary,
  stale,
  allowSkipErrors,
  setAllowSkipErrors,
  onDryRun,
  onImport,
  dryRunLoading,
  importLoading,
}: {
  updateExisting: boolean;
  setUpdateExisting: (value: boolean) => void;
  dryRunSummary: ImportSummary | null;
  stale: boolean;
  allowSkipErrors: boolean;
  setAllowSkipErrors: (value: boolean) => void;
  onDryRun: () => void;
  onImport: () => void;
  dryRunLoading: boolean;
  importLoading: boolean;
}) {
  const hasErrors = Boolean(dryRunSummary?.errors.length);
  const canImport = Boolean(dryRunSummary) && !stale && (!hasErrors || allowSkipErrors) && !importLoading;
  return <section className={styles.section} aria-labelledby="dry-run-heading">
    <div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 4{stale ? ' · параметры изменены' : ''}</p><h2 id="dry-run-heading">Проверочный запуск</h2><p>Сначала проверяем строки без записи в каталог. После проверки можно запустить итоговый импорт.</p></div></div>
    <div className={`${styles.options} ${styles.optionsSingle}`}>
      <div><Switch checked={updateExisting} onChange={setUpdateExisting} label="Обновлять существующие записи" /><span><strong>Обновлять существующие записи</strong><small>Изменять найденные записи по природным ключам листа</small></span></div>
    </div>
    {dryRunSummary ? <><Summary summary={dryRunSummary} />{hasErrors ? <label className={styles.skipErrors}><input type="checkbox" checked={allowSkipErrors} onChange={(event) => setAllowSkipErrors(event.target.checked)} />Пропустить строки с ошибками при итоговом импорте</label> : <p className={styles.successMessage} role="status">Критических ошибок не найдено. Импорт готов к подтверждению.</p>}</> : null}
    <div className={styles.runActions}><Button type="button" variant="orange" loading={dryRunLoading} disabled={dryRunLoading || importLoading} onClick={onDryRun}>Запустить dry-run</Button><Button type="button" variant="primary" data-testid="import-confirm" loading={importLoading} disabled={!canImport || dryRunLoading} title={stale ? 'Параметры изменены — перезапустите проверку' : undefined} onClick={onImport}>Импортировать</Button></div>
  </section>;
}

function JobDetails({ job, onClose }: { job: ImportJob; onClose: () => void }) {
  const summary = job.result;
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const download = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const { downloadImportReport } = await import('@/shared/lib/import-repository');
      const blob = await downloadImportReport(job.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `import_report_${job.id.slice(0, 8)}.xlsx`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (error) {
      setDownloadError(normalizeApiError(error, { fallbackMessage: 'Не удалось скачать отчёт импорта.' }).message);
    } finally { setDownloading(false); }
  };
  return <Drawer title="Детали импорта" onClose={onClose}><div className={styles.details}>
    <div className={styles.detailsTitle}><strong>{job.filename ?? 'Файл импорта'}</strong><StatusBadge intent={jobStatusMeta[job.status].intent}>{jobStatusMeta[job.status].label}</StatusBadge></div>
    <dl className={styles.detailsList}><div><dt>Лист</dt><dd>{job.sheet ?? '—'}</dd></div><div><dt>Создан</dt><dd>{formatDateTimeRu(job.createdAt)}</dd></div><div><dt>Кто</dt><dd>{job.createdBy ?? '—'}</dd></div><div><dt>Режим</dt><dd>{job.dryRun ? 'Dry-run' : 'Импорт'}</dd></div><div><dt>Прогресс</dt><dd>{job.progress === null ? '—' : `${job.progress}%`}</dd></div><div><dt>Всего строк</dt><dd>{summary?.total_rows ?? '—'}</dd></div><div><dt>Добавлено</dt><dd>{summary?.inserted ?? '—'}</dd></div><div><dt>Обновлено</dt><dd>{summary?.updated ?? '—'}</dd></div><div><dt>Пропущено</dt><dd>{summary?.skipped ?? '—'}</dd></div><div><dt>Ошибок</dt><dd>{summary?.errors_total ?? summary?.errors.length ?? '—'}</dd></div></dl>
    {summary?.truncated ? <p className={styles.muted}>Список ошибок сокращён; полное число показано выше.</p> : null}
    {job.error ? <FormErrorBanner>{job.error}</FormErrorBanner> : null}
    {job.errorReportUrl ? <Button type="button" variant="ghost" size="s" loading={downloading} onClick={() => void download()}>Скачать отчёт об ошибках</Button> : null}
    {downloadError ? <FormErrorBanner>{downloadError}</FormErrorBanner> : null}
    {summary?.errors.length ? <div className={styles.errors}><h3>Ошибки по строкам</h3><TableShell ariaLabel="Ошибки импорта"><table className={tableStyles.table}><thead><tr><th>Строка</th><th>Колонка</th><th>Ошибка</th></tr></thead><tbody>{summary.errors.map((item, index) => <tr key={`${item.row}-${item.field}-${index}`}><td>{item.row}</td><td>{item.sourceField ?? item.field}</td><td>{item.error}</td></tr>)}</tbody></table></TableShell></div> : null}
    {!summary && job.status === 'processing' ? <p className={styles.muted}>Результат появится после завершения обработки.</p> : null}
  </div></Drawer>;
}

function JobsJournal({ jobs, loading, error, onRetry, onSelect }: { jobs: ImportJob[]; loading: boolean; error: unknown; onRetry: () => void; onSelect: (job: ImportJob) => void }) {
  if (loading) return <div className={styles.loading} role="status">Загрузка журнала…</div>;
  if (error) { const normalized = normalizeApiError(error, { fallbackMessage: 'Не удалось загрузить журнал импортов.' }); return <ErrorState title={normalized.message} description="Попробуйте обновить журнал." headingLevel={3} onRetry={onRetry} />; }
  if (!jobs.length) return <p className={styles.empty}>Импорты ещё не запускались. Созданные задачи появятся здесь после подтверждения.</p>;
  return <TableShell ariaLabel="Журнал импортов"><div className={styles.jobsDesktop}><table className={tableStyles.table}><caption className={styles.visuallyHidden}>Журнал импортов</caption><thead><tr><th>Когда</th><th>Кто</th><th>Лист</th><th>Файл</th><th>Статус</th><th>Итоги</th><th>Действия</th></tr></thead><tbody>{jobs.map((job) => <tr data-testid="import-job-row" key={job.id}><td><time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time></td><td>{job.createdBy ?? '—'}</td><td>{job.sheet ?? '—'}</td><td>{job.filename ?? '—'}</td><td><StatusBadge intent={jobStatusMeta[job.status].intent}>{jobStatusMeta[job.status].label}</StatusBadge></td><td>{job.result ? `${job.result.inserted} доб. · ${job.result.updated} обн. · ${job.result.errors.length} ошибок` : '—'}</td><td><Button type="button" variant="ghost" size="s" onClick={() => onSelect(job)}>Подробнее</Button></td></tr>)}</tbody></table></div><div className={styles.jobsMobile}>{jobs.map((job) => <article data-testid="import-job-row" className={styles.jobCard} key={job.id} role="button" tabIndex={0} onClick={() => onSelect(job)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(job); } }}><div className={styles.jobCardHeader}><strong>{job.filename ?? 'Файл импорта'}</strong><StatusBadge intent={jobStatusMeta[job.status].intent}>{jobStatusMeta[job.status].label}</StatusBadge></div><small>{formatDateTimeRu(job.createdAt)} · {job.sheet ?? ''} · {job.createdBy ?? '—'}</small><span>{job.result ? `${job.result.inserted} добавлено · ${job.result.updated} обновлено` : 'Результат обрабатывается'}</span></article>)}</div></TableShell>;
}

export function ImportPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [upload, setUpload] = useState<ImportUploadResponse | null>(null);
  const [fileName, setFileName] = useState('');
  const [sheetId, setSheetId] = useState('');
  const [importAll, setImportAll] = useState(false);
  const [bulkDry, setBulkDry] = useState<BulkSheetResult[] | null>(null);
  const [bulkFinal, setBulkFinal] = useState<BulkSheetResult[] | null>(null);
  const [bulkRunning, setBulkRunning] = useState<'dry' | 'import' | null>(null);
  const [updateExisting, setUpdateExisting] = useState(true);
  const [dryStale, setDryStale] = useState(false);
  const [bulkStale, setBulkStale] = useState(false);
  const [allowSkipErrors, setAllowSkipErrors] = useState(false);
  const [dryRunSummary, setDryRunSummary] = useState<ImportSummary | null>(null);
  const [activeDryRunId, setActiveDryRunId] = useState<string | null>(null);
  const [submittedImportId, setSubmittedImportId] = useState<string | null>(null);
  const handledImportId = useRef<string | null>(null);
  const observedActiveJobs = useRef(new Set<string>());
  const [runKind, setRunKind] = useState<'dry-run' | 'import' | null>(null);
  const [selectedJob, setSelectedJob] = useState<ImportJob | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);

  const jobsQuery = useQuery({ queryKey: importQueryKeys.jobs, queryFn: listImportJobs, staleTime: Infinity });
  const baseJobs = useMemo(() => jobsQuery.data ?? [], [jobsQuery.data]);
  const addJob = useCallback((job: ImportJob) => {
    queryClient.setQueryData<ImportJob[]>(importQueryKeys.jobs, (current = []) => [job, ...current.filter((item) => item.id !== job.id)]);
    queryClient.setQueryData(importQueryKeys.job(job.id), job);
  }, [queryClient]);
  const activeJobs = baseJobs.filter(isImportJobActive);
  const statusQueries = useQueries({ queries: activeJobs.map((job) => ({
    queryKey: importQueryKeys.job(job.id),
    queryFn: async () => {
      const next = await getImportJob(job.id);
      queryClient.setQueryData<ImportJob[]>(importQueryKeys.jobs, (current = []) => current.map((item) => item.id === next.id ? { ...item, ...next, createdAt: item.createdAt, createdBy: item.createdBy ?? next.createdBy, filename: item.filename ?? next.filename, sheet: item.sheet ?? next.sheet } : item));
      return next;
    },
    retry: 2,
    refetchInterval: (query: { state: { data?: ImportJob } }) => {
      const current = query.state.data;
      return !current || isImportJobActive(current) ? 3000 : false;
    },
  })) });
  const jobs = useMemo(() => {
    const latest = new Map(statusQueries.flatMap((query) => query.data ? [[query.data.id, query.data] as const] : []));
    return baseJobs.map((job) => latest.has(job.id) ? { ...job, ...latest.get(job.id), createdAt: job.createdAt, createdBy: job.createdBy ?? latest.get(job.id)?.createdBy, filename: job.filename ?? latest.get(job.id)?.filename, sheet: job.sheet ?? latest.get(job.id)?.sheet } : job);
  }, [baseJobs, statusQueries]);

  useEffect(() => {
    if (!activeDryRunId) return;
    const completed = jobs.find((job) => job.id === activeDryRunId && !isImportJobActive(job));
    if (!completed) return;
    queueMicrotask(() => {
      setActiveDryRunId(null);
      if (completed.status === 'done' && completed.result) {
        setDryRunSummary(completed.result);
        setDryStale(false);
        setAllowSkipErrors(false);
        setToast({ intent: completed.result.errors.length ? 'info' : 'success', title: 'Проверочный запуск завершён', message: completed.result.errors.length ? `Найдено ошибок: ${completed.result.errors_total ?? completed.result.errors.length}.` : 'Данные готовы к импорту.' });
      } else if (completed.error) setActionError(completed.error);
    });
  }, [activeDryRunId, jobs]);

  useEffect(() => {
    if (!submittedImportId || handledImportId.current === submittedImportId) return;
    const completed = jobs.find((job) => job.id === submittedImportId && !isImportJobActive(job));
    if (!completed) return;
    handledImportId.current = submittedImportId;
    if (completed.status === 'done' && !completed.dryRun) {
      void invalidateImportedDomains(queryClient);
      queueMicrotask(() => setToast({ intent: 'success', title: 'Импорт завершён', message: `Добавлено: ${completed.result?.inserted ?? 0}, обновлено: ${completed.result?.updated ?? 0}, ошибок: ${completed.result?.errors_total ?? completed.result?.errors.length ?? 0}.` }));
    } else if (completed.error) queueMicrotask(() => setActionError(completed.error ?? 'Импорт не выполнен.'));
  }, [submittedImportId, jobs, queryClient]);

  useEffect(() => {
    for (const job of jobs) {
      if (isImportJobActive(job)) {
        observedActiveJobs.current.add(job.id);
      } else if (observedActiveJobs.current.delete(job.id) && job.id !== submittedImportId
        && job.status === 'done' && !job.dryRun) {
        void invalidateImportedDomains(queryClient);
      }
    }
  }, [jobs, queryClient, submittedImportId]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadImportFile(file),
    onSuccess: (data, file) => {
      setUpload(data);
      setFileName(file.name);
      setFileError(null);
      setDryRunSummary(null);
      setBulkDry(null);
      setBulkFinal(null);
      setActionError(null);
      const only = data.sheets.length === 1 ? data.sheets[0].id : '';
      setSheetId(only);
      setToast({ intent: 'success', title: 'Файл загружен', message: data.sheets.length ? `Найдено листов: ${data.sheets.length}. Выберите лист для импорта.` : 'В файле нет листов с данными.' });
    },
    onError: (cause) => setFileError(importActionError(cause, 'Не удалось загрузить файл.')),
  });

  const sheetPreviewQuery = useQuery({
    queryKey: [...importQueryKeys.preview(upload?.file_id ?? ''), sheetId],
    queryFn: () => previewImportSheet(upload!.file_id, sheetId),
    enabled: Boolean(upload && sheetId),
    staleTime: Infinity,
  });
  const preview = sheetPreviewQuery.data ?? null;

  const runMutation = useMutation({
    mutationFn: ({ fileId, sheet, dryRun }: { fileId: string; sheet: string; dryRun: boolean }) =>
      executeSheetImport(fileId, sheet, { dry_run: dryRun, update_existing: updateExisting, filename: fileName }),
    onSuccess: (data, variables) => {
      const job = adaptImportJob({ job_id: data.job_id, status: 'queued', dry_run: variables.dryRun, filename: fileName, sheet: variables.sheet, created_by: user?.name });
      addJob(job);
      if (variables.dryRun) setActiveDryRunId(data.job_id);
      else { handledImportId.current = null; setSubmittedImportId(data.job_id); setToast({ intent: 'info', title: 'Импорт поставлен в очередь', message: 'Статус задачи обновляется автоматически.' }); }
      setRunKind(null);
      setActionError(null);
    },
    onError: (cause) => { setRunKind(null); setActionError(normalizeApiError(cause, { fallbackMessage: 'Не удалось запустить импорт.' }).message); },
  });

  const acceptFile = (file: File) => { setFileError(null); uploadMutation.mutate(file); };
  const chooseSheet = (value: string) => { setSheetId(value); setDryRunSummary(null); setDryStale(false); setActionError(null); };
  const changeUpdateExisting = (value: boolean) => {
    setUpdateExisting(value);
    if (dryRunSummary) setDryStale(true);
    if (bulkDry) setBulkStale(true);
  };
  const toggleImportAll = (value: boolean) => {
    setImportAll(value);
    setSheetId('');
    setDryRunSummary(null);
    setBulkDry(null);
    setBulkFinal(null);
    setActionError(null);
  };
  const runBulk = async (dry: boolean) => {
    if (!upload || bulkRunning) return;
    setBulkRunning(dry ? 'dry' : 'import');
    setActionError(null);
    if (dry) setBulkFinal(null);
    else setBulkDry(null);
    const ordered = sortSheetsForImport(upload.sheets);
    const labelOf = (id: string) => ordered.find((sheet) => sheet.id === id)?.label ?? id;
    try {
      const { job_id } = await executeSheetsImport(upload.file_id, ordered.map((sheet) => sheet.id), { dry_run: dry, update_existing: updateExisting, filename: fileName });
      addJob(adaptImportJob({ job_id, status: 'queued', dry_run: dry, filename: fileName, sheet: `Все листы (${ordered.length})`, created_by: user?.name }));
      const job = await waitForImportJob(job_id);
      const breakdown: BulkSheetResult[] = (job.result?.sheets ?? []).map((item) => ({
        sheetId: item.sheet,
        label: labelOf(item.sheet),
        summary: item.summary,
        error: item.error,
      }));
      if (dry) {
        setBulkDry(breakdown);
        setBulkStale(false);
        const errors = breakdown.reduce((total, item) => total + (item.summary?.errors_total ?? item.summary?.errors.length ?? 0), 0);
        setToast({ intent: errors ? 'info' : 'success', title: 'Проверка всех листов завершена', message: errors ? `Найдено ошибок: ${errors}.` : 'Данные готовы к импорту.' });
      } else {
        setBulkFinal(breakdown);
        const failed = breakdown.some((item) => item.error) || job.status === 'failed';
        if (!failed) {
          await invalidateImportedDomains(queryClient);
          const inserted = breakdown.reduce((total, item) => total + (item.summary?.inserted ?? 0), 0);
          const errors = breakdown.reduce((total, item) => total + (item.summary?.errors_total ?? item.summary?.errors.length ?? 0), 0);
          setToast({ intent: errors ? 'info' : 'success', title: 'Импорт всех листов завершён', message: `Добавлено: ${inserted}, ошибок: ${errors}.` });
        } else {
          setActionError(job.error ?? 'Импорт всех листов завершился с ошибкой.');
        }
      }
    } catch (cause) {
      setActionError(normalizeApiError(cause, { fallbackMessage: 'Не удалось выполнить импорт.' }).message);
    } finally {
      setBulkRunning(null);
    }
  };
  const runDryRun = () => { if (!upload || !sheetId) return; setRunKind('dry-run'); runMutation.mutate({ fileId: upload.file_id, sheet: sheetId, dryRun: true }); };
  const runImport = () => { if (!upload || !sheetId || !dryRunSummary || (dryRunSummary.errors.length > 0 && !allowSkipErrors)) return; setRunKind('import'); runMutation.mutate({ fileId: upload.file_id, sheet: sheetId, dryRun: false }); };
  const activeStep = importAll ? (!upload ? 0 : bulkFinal ? 3 : 1) : currentStep(upload, sheetId, preview, dryRunSummary);
  const selectedSheet = upload?.sheets.find((sheet) => sheet.id === sheetId);
  const orderedSheets = useMemo(() => (upload ? sortSheetsForImport(upload.sheets) : []), [upload]);
  const bulkCanImport = Boolean(bulkDry && bulkDry.length === orderedSheets.length)
    && !bulkStale
    && (bulkDry?.every((item) => !item.error && ((item.summary?.errors_total ?? item.summary?.errors.length ?? 1) === 0)) || allowSkipErrors)
    && bulkRunning !== 'import';

  return <div className={styles.page}>
    <StepRail active={activeStep} />
    <section className={styles.section} aria-labelledby="import-file-heading"><div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 1</p><h2 id="import-file-heading">Файл</h2><p>Загрузите Excel-файл. Сервер прочитает листы и покажет их списком.</p></div></div><FileDropzone onFile={acceptFile} loading={uploadMutation.isPending} error={fileError} /><div className={styles.demoFile}><ButtonAnchor href="/demo/CRM_import_filled.xlsx" download="CRM_import_filled.xlsx" variant="secondary" size="s">↓ Скачать тестовый файл</ButtonAnchor><span>Можно использовать готовый пример для проверки импорта.</span></div>{fileName ? <p className={styles.fileSelected} role="status">Выбран файл: <strong>{fileName}</strong></p> : null}</section>
    {upload ? <section className={styles.section} aria-labelledby="import-sheet-heading"><div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 2</p><h2 id="import-sheet-heading">Лист</h2><p>Выберите один лист или импортируйте весь файл сразу. Сопоставление колонок выполняет сервер.</p></div></div><div className={`${styles.options} ${styles.optionsSingle}`}><div><Switch checked={importAll} onChange={toggleImportAll} label="Все листы файла" /><span><strong>Все листы файла</strong><small>Импорт всех листов по порядку зависимостей</small></span></div></div>{importAll ? <TableShell ariaLabel="Листы файла"><div className={styles.previewDesktop}><table className={tableStyles.table}><caption className={styles.visuallyHidden}>Листы файла в порядке импорта</caption><thead><tr><th scope="col">Порядок</th><th scope="col">Лист</th><th scope="col">Строк</th></tr></thead><tbody>{orderedSheets.map((sheet, index) => <tr key={sheet.id}><td>{index + 1}</td><td>{sheet.label}</td><td>{sheet.row_count}</td></tr>)}</tbody></table></div></TableShell> : <><Select aria-label="Лист для импорта" data-testid="sheet-select" value={sheetId} onChange={(event) => chooseSheet(event.target.value)}><option value="">Выберите лист</option>{upload.sheets.map((sheet) => <option key={sheet.id} value={sheet.id}>{sheet.label} · строк: {sheet.row_count}</option>)}</Select>{selectedSheet ? <p className={styles.hint}>«{selectedSheet.label}»: строк данных {selectedSheet.row_count}.</p> : null}</>}{!importAll && sheetPreviewQuery.isPending ? <p className={styles.loading} role="status">Строим предпросмотр…</p> : null}{!importAll && sheetPreviewQuery.error ? <FormErrorBanner>{importActionError(sheetPreviewQuery.error, 'Не удалось построить предпросмотр листа.')}</FormErrorBanner> : null}</section> : null}
    {!importAll && preview ? <SheetPreview preview={preview} summary={dryRunSummary} /> : null}
    {importAll && upload ? <section className={styles.section} aria-labelledby="bulk-run-heading"><div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 3–4{bulkStale ? ' · параметры изменены' : ''}</p><h2 id="bulk-run-heading">Проверка и запуск всех листов</h2><p>Листы обрабатываются по порядку зависимостей. При ошибке задачи цепочка останавливается.</p></div></div><div className={`${styles.options} ${styles.optionsSingle}`}><div><Switch checked={updateExisting} onChange={changeUpdateExisting} label="Обновлять существующие записи" /><span><strong>Обновлять существующие записи</strong><small>Изменять найденные записи по природным ключам листов</small></span></div></div><div className={styles.runActions}><Button type="button" variant="orange" loading={bulkRunning === 'dry'} disabled={bulkRunning !== null} onClick={() => void runBulk(true)}>Проверить всё</Button><Button type="button" variant="primary" data-testid="import-all-confirm" loading={bulkRunning === 'import'} disabled={!bulkCanImport || bulkRunning !== null} onClick={() => void runBulk(false)}>Импортировать всё</Button></div>{bulkRunning ? <p className={styles.loading} role="status">{bulkRunning === 'dry' ? 'Проверяем листы…' : 'Импортируем листы…'}</p> : null}{bulkDry ? <BulkResults results={bulkDry} /> : null}{bulkFinal ? <BulkResults results={bulkFinal} /> : null}{bulkDry && bulkDry.some((item) => (item.summary?.errors_total ?? item.summary?.errors.length ?? 0) > 0) ? <label className={styles.skipErrors}><input type="checkbox" checked={allowSkipErrors} onChange={(event) => setAllowSkipErrors(event.target.checked)} />Пропустить строки с ошибками при итоговом импорте</label> : null}</section> : null}
    {!importAll && preview ? <OptionsAndRun updateExisting={updateExisting} setUpdateExisting={changeUpdateExisting} dryRunSummary={dryRunSummary} stale={dryStale} allowSkipErrors={allowSkipErrors} setAllowSkipErrors={setAllowSkipErrors} onDryRun={runDryRun} onImport={runImport} dryRunLoading={runMutation.isPending && runKind === 'dry-run'} importLoading={runMutation.isPending && runKind === 'import'} /> : null}
    {actionError ? <FormErrorBanner>{actionError}</FormErrorBanner> : null}
    <section className={`${styles.section} ${styles.journal}`} aria-labelledby="import-jobs-heading"><div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Журнал</p><h2 id="import-jobs-heading">Импорты</h2><p>Задачи в очереди и в обработке обновляются автоматически каждые 3 секунды.</p></div><Button type="button" variant="ghost" size="s" onClick={() => void jobsQuery.refetch()}>Обновить</Button></div><JobsJournal jobs={jobs} loading={jobsQuery.isPending} error={jobsQuery.error} onRetry={() => void jobsQuery.refetch()} onSelect={setSelectedJob} /></section>
    {selectedJob ? <JobDetails job={jobs.find((job) => job.id === selectedJob.id) ?? selectedJob} onClose={() => setSelectedJob(null)} /> : null}
    {toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : null}
  </div>;
}
