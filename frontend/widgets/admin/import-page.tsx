'use client';

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatDateTimeRu } from '@/shared/lib/formatters';
import { ApiRequestError, normalizeApiError } from '@/shared/lib/api-errors';
import {
  adaptImportJob,
  autoMapImportHeaders,
  downloadImportReport,
  executeImport,
  getImportJob,
  importCatalogOptions,
  importQueryKeys,
  importTargetLabel,
  isImportJobActive,
  listImportJobs,
  requiredImportFields,
  targetFieldsForCatalog,
  uploadImportPreview,
  type ImportCatalogType,
  type ImportJob,
  type ImportPreviewResponse,
  type ImportSummary,
} from '@/shared/lib/import-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { ErrorState } from '@/shared/ui/error-state';
import { FormError, FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { Select, Switch } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import styles from './import-page.module.css';

const steps = ['Тип справочника', 'Файл', 'Маппинг', 'Preview', 'Dry-run', 'Подтверждение'];
const mappingStoragePrefix = 'import.mapping.v1:';

const jobStatusMeta: Record<ImportJob['status'], { label: string; intent: 'neutral' | 'info' | 'success' | 'danger' }> = {
  queued: { label: 'В очереди', intent: 'neutral' },
  processing: { label: 'Обработка', intent: 'info' },
  done: { label: 'Готово', intent: 'success' },
  failed: { label: 'Ошибка', intent: 'danger' },
};

function currentStep(catalogType: ImportCatalogType | '', preview: ImportPreviewResponse | null, mappingReady: boolean, dryRunSummary: ImportSummary | null): number {
  if (!catalogType) return 0;
  if (!preview) return 1;
  if (!mappingReady) return 2;
  if (!dryRunSummary) return 3;
  return 5;
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function errorKey(row: number, field: string): string {
  return `${row}:${field}`;
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
    <div><strong>{summary.inserted}</strong><span>Добавлено</span></div>
    <div><strong>{summary.updated}</strong><span>Обновлено</span></div>
    <div><strong>{summary.skipped}</strong><span>Пропущено</span></div>
    <div className={summary.errors.length ? styles.summaryError : ''}><strong>{summary.errors.length}</strong><span>Ошибок</span></div>
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
      <strong>{loading ? 'Проверяем файл…' : 'Перетащите XLSX сюда или выберите файл'}</strong>
      <small>Поддерживаются .xlsx и .xls, размер до 10 МБ</small>
    </label>
    {error ? <FormError id="import-file-error">{error}</FormError> : null}
  </div>;
}

function MappingEditor({
  preview,
  catalogType,
  mapping,
  onChange,
  onAutoMap,
  onReset,
}: {
  preview: ImportPreviewResponse;
  catalogType: ImportCatalogType;
  mapping: Record<string, string>;
  onChange: (source: string, target: string) => void;
  onAutoMap: () => void;
  onReset: () => void;
}) {
  const missing = requiredImportFields[catalogType].filter((field) => !Object.values(mapping).includes(field));
  const usedByOther = (target: string, source: string) => Object.entries(mapping).some(([key, value]) => key !== source && value === target);
  return <section className={styles.section} aria-labelledby="mapping-heading">
    <div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 3</p><h2 id="mapping-heading">Сопоставление колонок</h2><p>Проверьте, какое поле системы соответствует каждой колонке файла. Для каждой колонки доступны первые три значения.</p></div><div className={styles.mappingActions}><Button type="button" size="s" variant="secondary" onClick={onAutoMap}>Автомаппинг</Button><Button type="button" size="s" variant="ghost" onClick={onReset}>Сбросить</Button></div></div>
    {missing.length ? <FormErrorBanner>Не выбраны обязательные поля: {missing.map(importTargetLabel).join(', ')}. Заполните их, чтобы продолжить.</FormErrorBanner> : <p className={styles.mappingReady} role="status">Обязательные поля сопоставлены. Можно проверить первые строки.</p>}
    <div className={styles.mappingList}>{preview.headers.map((source, index) => <div className={styles.mappingRow} key={source}>
      <div className={styles.sourceColumn}><strong>{source || `Колонка ${index + 1}`}</strong><div className={styles.examples}>{preview.preview.slice(0, 3).map((row, exampleIndex) => <span key={`${source}-${exampleIndex}`}>{valueText(row[source])}</span>)}</div></div>
      <span className={styles.mappingArrow} aria-hidden="true">→</span>
      <Select aria-label={`Поле системы для ${source}`} data-testid={`mapping-select-${index}`} value={mapping[source] ?? ''} onChange={(event) => onChange(source, event.target.value)}>
        <option value="">Не сопоставлять</option>
        {targetFieldsForCatalog(catalogType).map((field) => <option key={field.id} value={field.id} disabled={usedByOther(field.id, source)}>{field.label}</option>)}
      </Select>
    </div>)}</div>
  </section>;
}

function MappedPreview({ preview, mapping, summary }: { preview: ImportPreviewResponse; mapping: Record<string, string>; summary: ImportSummary | null }) {
  const mappedColumns = preview.headers.filter((header) => mapping[header]);
  const errors = new Map((summary?.errors ?? []).map((item) => [errorKey(item.row, item.field), item.error]));
  return <section className={styles.section} aria-labelledby="preview-heading">
    <div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 4</p><h2 id="preview-heading">Preview данных</h2><p>Первые {Math.min(10, preview.preview.length)} строк с применённым сопоставлением из {preview.row_count}.</p></div></div>
    <TableShell className={styles.previewShell} ariaLabel="Предпросмотр импорта"><div className={styles.previewDesktop}><table data-testid="preview-table"><caption className={styles.visuallyHidden}>Первые строки файла после сопоставления</caption><thead><tr><th scope="col">Строка</th>{mappedColumns.map((header) => <th scope="col" key={header}>{importTargetLabel(mapping[header])}</th>)}</tr></thead><tbody>{preview.preview.slice(0, 10).map((row, index) => <tr key={index}>{<td>{index + 2}</td>}{mappedColumns.map((header) => { const field = mapping[header]; const error = errors.get(errorKey(index + 2, field)); return <td className={error ? styles.cellError : undefined} title={error} key={`${index}-${header}`}>{valueText(row[header])}</td>; })}</tr>)}</tbody></table></div><div className={styles.previewMobile}>{preview.preview.slice(0, 10).map((row, index) => <article key={index}><strong>Строка {index + 2}</strong><dl>{mappedColumns.map((header) => <div key={header}><dt>{importTargetLabel(mapping[header])}</dt><dd>{valueText(row[header])}</dd></div>)}</dl></article>)}</div></TableShell>
  </section>;
}

function OptionsAndRun({
  updateExisting,
  setUpdateExisting,
  skipHeader,
  setSkipHeader,
  dryRun,
  setDryRun,
  dryRunSummary,
  allowSkipErrors,
  setAllowSkipErrors,
  onDryRun,
  onImport,
  dryRunLoading,
  importLoading,
}: {
  updateExisting: boolean;
  setUpdateExisting: (value: boolean) => void;
  skipHeader: boolean;
  setSkipHeader: (value: boolean) => void;
  dryRun: boolean;
  setDryRun: (value: boolean) => void;
  dryRunSummary: ImportSummary | null;
  allowSkipErrors: boolean;
  setAllowSkipErrors: (value: boolean) => void;
  onDryRun: () => void;
  onImport: () => void;
  dryRunLoading: boolean;
  importLoading: boolean;
}) {
  const hasErrors = Boolean(dryRunSummary?.errors.length);
  const canImport = Boolean(dryRunSummary) && (!hasErrors || allowSkipErrors) && !importLoading;
  return <section className={styles.section} aria-labelledby="dry-run-heading">
    <div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 5</p><h2 id="dry-run-heading">Проверочный запуск</h2><p>Сначала проверяем строки без записи в каталог. После проверки можно запустить итоговый импорт.</p></div></div>
    <div className={styles.options}>
      <div><Switch checked={updateExisting} onChange={setUpdateExisting} label="Обновлять существующие записи" /><span><strong>Обновлять существующие записи</strong><small>Изменять найденные записи выбранного типа по ключу сопоставления</small></span></div>
      <div><Switch checked={skipHeader} onChange={setSkipHeader} label="Пропустить строку заголовков" /><span><strong>Пропустить строку заголовков</strong><small>Первая строка используется как названия колонок</small></span></div>
      <div><Switch checked={dryRun} onChange={setDryRun} label="Проверочный запуск" testId="dry-run-toggle" /><span><strong>Проверочный запуск</strong><small>Не сохранять изменения при первой проверке</small></span></div>
    </div>
    {dryRunSummary ? <><Summary summary={dryRunSummary} />{hasErrors ? <label className={styles.skipErrors}><input type="checkbox" checked={allowSkipErrors} onChange={(event) => setAllowSkipErrors(event.target.checked)} />Пропустить строки с ошибками при итоговом импорте</label> : <p className={styles.successMessage} role="status">Критических ошибок не найдено. Импорт готов к подтверждению.</p>}</> : null}
    <div className={styles.runActions}><Button type="button" variant="orange" loading={dryRunLoading} disabled={dryRunLoading || importLoading} onClick={onDryRun}>Запустить dry-run</Button><Button type="button" variant="primary" data-testid="import-confirm" loading={importLoading} disabled={!canImport || dryRunLoading} onClick={onImport}>Импортировать</Button></div>
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
    <dl className={styles.detailsList}><div><dt>Создан</dt><dd>{formatDateTimeRu(job.createdAt)}</dd></div><div><dt>Кто</dt><dd>{job.createdBy ?? '—'}</dd></div><div><dt>Всего строк</dt><dd>{summary?.total_rows ?? '—'}</dd></div><div><dt>Добавлено</dt><dd>{summary?.inserted ?? '—'}</dd></div><div><dt>Обновлено</dt><dd>{summary?.updated ?? '—'}</dd></div><div><dt>Пропущено</dt><dd>{summary?.skipped ?? '—'}</dd></div></dl>
    {job.error ? <FormErrorBanner>{job.error}</FormErrorBanner> : null}
    {job.errorReportUrl ? <Button type="button" variant="ghost" size="s" loading={downloading} onClick={() => void download()}>Скачать отчёт об ошибках</Button> : null}
    {downloadError ? <FormErrorBanner>{downloadError}</FormErrorBanner> : null}
    {summary?.errors.length ? <div className={styles.errors}><h3>Ошибки по строкам</h3><TableShell ariaLabel="Ошибки импорта"><table><thead><tr><th>Строка</th><th>Поле</th><th>Ошибка</th></tr></thead><tbody>{summary.errors.map((item, index) => <tr key={`${item.row}-${item.field}-${index}`}><td>{item.row}</td><td>{importTargetLabel(item.field)}</td><td>{item.error}</td></tr>)}</tbody></table></TableShell></div> : null}
    {!summary && job.status === 'processing' ? <p className={styles.muted}>Результат появится после завершения обработки.</p> : null}
  </div></Drawer>;
}

function JobsJournal({ jobs, loading, error, onRetry, onSelect }: { jobs: ImportJob[]; loading: boolean; error: unknown; onRetry: () => void; onSelect: (job: ImportJob) => void }) {
  if (loading) return <div className={styles.loading} role="status">Загрузка журнала…</div>;
  if (error) { const normalized = normalizeApiError(error, { fallbackMessage: 'Не удалось загрузить журнал импортов.' }); return <ErrorState title={normalized.message} description="Попробуйте обновить журнал." headingLevel={3} onRetry={onRetry} />; }
  if (!jobs.length) return <p className={styles.empty}>Импорты ещё не запускались. Созданные задачи появятся здесь после подтверждения.</p>;
  return <TableShell ariaLabel="Журнал импортов"><div className={styles.jobsDesktop}><table><caption className={styles.visuallyHidden}>Журнал импортов</caption><thead><tr><th>Когда</th><th>Кто</th><th>Тип</th><th>Файл</th><th>Статус</th><th>Итоги</th><th>Действия</th></tr></thead><tbody>{jobs.map((job) => <tr data-testid="import-job-row" key={job.id}><td><time dateTime={job.createdAt}>{formatDateTimeRu(job.createdAt)}</time></td><td>{job.createdBy ?? '—'}</td><td>{importCatalogOptions.find((item) => item.id === job.catalogType)?.label ?? 'Каталог'}</td><td>{job.filename ?? '—'}</td><td><StatusBadge intent={jobStatusMeta[job.status].intent}>{jobStatusMeta[job.status].label}</StatusBadge></td><td>{job.result ? `${job.result.inserted} доб. · ${job.result.updated} обн. · ${job.result.errors.length} ошибок` : '—'}</td><td><Button type="button" variant="ghost" size="s" onClick={() => onSelect(job)}>Подробнее</Button></td></tr>)}</tbody></table></div><div className={styles.jobsMobile}>{jobs.map((job) => <article data-testid="import-job-row" className={styles.jobCard} key={job.id} role="button" tabIndex={0} onClick={() => onSelect(job)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(job); } }}><div className={styles.jobCardHeader}><strong>{job.filename ?? 'Файл импорта'}</strong><StatusBadge intent={jobStatusMeta[job.status].intent}>{jobStatusMeta[job.status].label}</StatusBadge></div><small>{formatDateTimeRu(job.createdAt)} · {job.createdBy ?? '—'}</small><span>{job.result ? `${job.result.inserted} добавлено · ${job.result.updated} обновлено` : 'Результат обрабатывается'}</span></article>)}</div></TableShell>;
}

export function ImportPage({ initialCatalogType = '' }: { initialCatalogType?: ImportCatalogType | '' }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [catalogType, setCatalogType] = useState<ImportCatalogType | ''>(initialCatalogType);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [fileName, setFileName] = useState('');
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [updateExisting, setUpdateExisting] = useState(true);
  const [skipHeader, setSkipHeader] = useState(true);
  const [dryRun, setDryRun] = useState(true);
  const [allowSkipErrors, setAllowSkipErrors] = useState(false);
  const [dryRunSummary, setDryRunSummary] = useState<ImportSummary | null>(null);
  const [activeDryRunId, setActiveDryRunId] = useState<string | null>(null);
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
      queryClient.setQueryData<ImportJob[]>(importQueryKeys.jobs, (current = []) => current.map((item) => item.id === next.id ? { ...item, ...next, createdAt: item.createdAt, createdBy: item.createdBy ?? next.createdBy, filename: item.filename ?? next.filename, catalogType: item.catalogType ?? next.catalogType } : item));
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
    return baseJobs.map((job) => latest.has(job.id) ? { ...job, ...latest.get(job.id), createdAt: job.createdAt, createdBy: job.createdBy ?? latest.get(job.id)?.createdBy, filename: job.filename ?? latest.get(job.id)?.filename, catalogType: job.catalogType ?? latest.get(job.id)?.catalogType } : job);
  }, [baseJobs, statusQueries]);

  useEffect(() => {
    if (!activeDryRunId) return;
    const completed = jobs.find((job) => job.id === activeDryRunId && !isImportJobActive(job));
    if (!completed) return;
    queueMicrotask(() => {
      setActiveDryRunId(null);
      if (completed.status === 'done' && completed.result) {
        setDryRunSummary(completed.result);
        setAllowSkipErrors(false);
        setToast({ intent: completed.result.errors.length ? 'info' : 'success', title: 'Проверочный запуск завершён', message: completed.result.errors.length ? `Найдено ошибок: ${completed.result.errors.length}.` : 'Данные готовы к импорту.' });
      } else if (completed.error) setActionError(completed.error);
    });
  }, [activeDryRunId, jobs]);

  useEffect(() => {
    if (!catalogType || typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(`${mappingStoragePrefix}${catalogType}`);
      if (!raw) return;
      const parsed = JSON.parse(raw) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return;
      const valid = Object.fromEntries(Object.entries(parsed as Record<string, unknown>).filter(([source, target]) => Boolean(preview?.headers.includes(source)) && typeof target === 'string' && targetFieldsForCatalog(catalogType).some((field) => field.id === target))) as Record<string, string>;
      if (Object.keys(valid).length) queueMicrotask(() => setMapping(valid));
    } catch { /* localStorage may be disabled; mapping remains editable */ }
  }, [catalogType, preview?.headers]);

  useEffect(() => {
    if (!catalogType || !Object.keys(mapping).length || typeof window === 'undefined') return;
    try { window.localStorage.setItem(`${mappingStoragePrefix}${catalogType}`, JSON.stringify(mapping)); } catch { /* ignore storage quota/private mode */ }
  }, [catalogType, mapping]);

  const uploadMutation = useMutation({ mutationFn: (file: File) => uploadImportPreview(file), onSuccess: (data, file) => { setPreview(data); setFileName(file.name); setFileError(null); setMapping({}); setDryRunSummary(null); setActionError(null); setToast({ intent: 'success', title: 'Файл загружен', message: `Найдено строк: ${data.row_count}.` }); }, onError: (cause) => setFileError(importActionError(cause, 'Не удалось загрузить файл.')) });
  const runMutation = useMutation({ mutationFn: ({ fileId, dryRun: nextDryRun }: { fileId: string; dryRun: boolean }) => executeImport(fileId, mapping, { skip_header: skipHeader, update_existing: updateExisting, dry_run: nextDryRun, catalog_type: catalogType || 'licenses', filename: fileName }), onSuccess: (data, variables) => { const job = adaptImportJob({ job_id: data.job_id, status: 'queued', filename: fileName, created_by: user?.name, catalog_type: catalogType }); addJob(job); if (variables.dryRun) setActiveDryRunId(data.job_id); else setToast({ intent: 'success', title: 'Импорт поставлен в журнал', message: 'Статус задачи обновляется автоматически.' }); setRunKind(null); setActionError(null); }, onError: (cause) => { setRunKind(null); setActionError(normalizeApiError(cause, { fallbackMessage: 'Не удалось запустить импорт.' }).message); } });

  const mappingReady = Boolean(catalogType) && requiredImportFields[catalogType || 'licenses'].every((field) => Object.values(mapping).includes(field));
  const activeStep = currentStep(catalogType, preview, mappingReady, dryRunSummary);
  const acceptFile = (file: File) => { setFileError(null); uploadMutation.mutate(file); };
  const onMappingChange = (source: string, target: string) => { setMapping((current) => { const next = { ...current }; if (target) next[source] = target; else delete next[source]; return next; }); setDryRunSummary(null); };
  const resetMapping = () => { setMapping({}); setDryRunSummary(null); };
  const runDryRun = () => { if (!preview || !mappingReady) return; setDryRun(true); setRunKind('dry-run'); runMutation.mutate({ fileId: preview.file_id, dryRun: true }); };
  const runImport = () => { if (!preview || !dryRunSummary || (dryRunSummary.errors.length > 0 && !allowSkipErrors)) return; setRunKind('import'); runMutation.mutate({ fileId: preview.file_id, dryRun: false }); };

  return <div className={styles.page}>
    <StepRail active={activeStep} />
    <section className={styles.section} aria-labelledby="import-type-heading"><div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 1</p><h2 id="import-type-heading">Тип справочника</h2><p>Выберите каталог, который нужно обновить.</p></div></div><Select aria-label="Тип справочника" value={catalogType} onChange={(event) => { setCatalogType(event.target.value as ImportCatalogType | ''); setPreview(null); setMapping({}); setDryRunSummary(null); setFileName(''); }}><option value="">Выберите тип справочника</option>{importCatalogOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</Select>{catalogType ? <p className={styles.hint}>{importCatalogOptions.find((item) => item.id === catalogType)?.description}</p> : null}</section>
    {catalogType ? <section className={styles.section} aria-labelledby="import-file-heading"><div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Шаг 2</p><h2 id="import-file-heading">Файл</h2><p>Загрузите Excel-файл. Сервер проверит структуру и вернёт первые строки.</p></div></div><FileDropzone onFile={acceptFile} loading={uploadMutation.isPending} error={fileError} />{fileName ? <p className={styles.fileSelected} role="status">Выбран файл: <strong>{fileName}</strong></p> : null}</section> : null}
    {preview && catalogType ? <MappingEditor preview={preview} catalogType={catalogType} mapping={mapping} onChange={onMappingChange} onAutoMap={() => { setMapping(autoMapImportHeaders(preview.headers, catalogType)); setDryRunSummary(null); }} onReset={resetMapping} /> : null}
    {preview && mappingReady ? <MappedPreview preview={preview} mapping={mapping} summary={dryRunSummary} /> : null}
    {preview && mappingReady ? <OptionsAndRun updateExisting={updateExisting} setUpdateExisting={(value) => { setUpdateExisting(value); setDryRunSummary(null); }} skipHeader={skipHeader} setSkipHeader={(value) => { setSkipHeader(value); setDryRunSummary(null); }} dryRun={dryRun} setDryRun={setDryRun} dryRunSummary={dryRunSummary} allowSkipErrors={allowSkipErrors} setAllowSkipErrors={setAllowSkipErrors} onDryRun={runDryRun} onImport={runImport} dryRunLoading={runMutation.isPending && runKind === 'dry-run'} importLoading={runMutation.isPending && runKind === 'import'} /> : null}
    {actionError ? <FormErrorBanner>{actionError}</FormErrorBanner> : null}
    <section className={`${styles.section} ${styles.journal}`} aria-labelledby="import-jobs-heading"><div className={styles.sectionHeader}><div><p className={styles.eyebrow}>Журнал</p><h2 id="import-jobs-heading">Импорты</h2><p>Задачи в очереди и в обработке обновляются автоматически каждые 3 секунды.</p></div><Button type="button" variant="ghost" size="s" onClick={() => void jobsQuery.refetch()}>Обновить</Button></div><JobsJournal jobs={jobs} loading={jobsQuery.isPending} error={jobsQuery.error} onRetry={() => void jobsQuery.refetch()} onSelect={setSelectedJob} /></section>
    {selectedJob ? <JobDetails job={jobs.find((job) => job.id === selectedJob.id) ?? selectedJob} onClose={() => setSelectedJob(null)} /> : null}
    {toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : null}
  </div>;
}
