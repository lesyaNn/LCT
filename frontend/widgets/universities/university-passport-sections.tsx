'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Download from '@atomaro/icons/24/action/Download';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import Mail from '@atomaro/icons/24/communication/Mail';
import Phone from '@atomaro/icons/24/technology/Phone';
import { Button } from '@/shared/ui/rtk/button';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { EmptyState } from '@/shared/ui/empty-state';
import { Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { MetricCard } from '@/shared/ui/rtk/metric-card';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Toast } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { adminUsersQueryKeys, assignUniversityResponsible, listResponsibleCandidates } from '@/shared/lib/users-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import {
  createWorkflowFromExternal,
  getUniversityExternalData,
  isExternalSourceUnavailable,
  universityExternalDataQueryKey,
  type ExternalApplication,
  type ExternalStudent,
} from '@/shared/lib/external-integrations-repository';
import { documentStatusIntent, licenseStatusIntent, productStatusIntent, programStatusIntent, readinessSemantics } from '@/shared/lib/status-semantics';
import {
  getUniversityProducts,
  getUniversityPrograms,
  getUniversityLicenses,
  getUniversityDocuments,
  getUniversityMeetings,
  getUniversityResponsibles,
  getUniversityStudentsSummary,
  getUniversityTeachers,
  programStatusLabels,
  universityProductsQueryKey,
  universityProgramsQueryKey,
  universityLicensesQueryKey,
  universityDocumentsQueryKey,
  universityMeetingsQueryKey,
  universityPassportQueryKey,
  universityResponsiblesQueryKey,
  universityStudentsQueryKey,
  universityTeachersQueryKey,
  type ProgramStatus,
  type TeacherReadiness,
  type UniversityProductRow,
  type UniversityProductStatus,
  type UniversityProgramRow,
  type UniversityStudentsByProgram,
  type UniversityTeacherRow,
  type UniversityLicenseRow,
  type UniversityLicenseStatus,
  type UniversityDocumentRow,
  type UniversityDocumentStatus,
  type UniversityMeetingRow,
  type UniversityMeetingType,
} from '@/shared/lib/universities-repository';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from './passport-data-table';
import { ReadinessBadge } from '@/shared/ui/rtk/readiness-badge';
import styles from './university-passport-sections.module.css';

const formatDate = formatDateRu;

function SectionToolbar({ title, children }: { title?: string; children: ReactNode }) {
  return <div className={styles.sectionToolbar}>{title ? <h2>{title}</h2> : null}<div className={styles.toolbarControls}>{children}</div></div>;
}

const productStatusLabels: Record<UniversityProductStatus, string> = {
  active: 'Действует',
  expiring: 'Истекает',
  expired: 'Просрочена',
};

function ProgramStatusBadge({ status }: { status: ProgramStatus }) {
  return <StatusBadge intent={programStatusIntent[status]}>{programStatusLabels[status]}</StatusBadge>;
}

function ProductStatusBadge({ status }: { status: UniversityProductStatus }) {
  return <StatusBadge intent={productStatusIntent[status]}>{productStatusLabels[status]}</StatusBadge>;
}

function ProgramFilter({ value, onChange }: { value: ProgramStatus | 'all'; onChange: (value: ProgramStatus | 'all') => void }) {
  return <label className={styles.filter}><span>Статус</span><select value={value} onChange={(event) => onChange(event.target.value as ProgramStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(programStatusLabels).map(([status, label]) => <option value={status} key={status}>{label}</option>)}</select></label>;
}

function TeacherFilter({ value, onChange }: { value: TeacherReadiness | 'all'; onChange: (value: TeacherReadiness | 'all') => void }) {
  return <label className={styles.filter}><span>Готовность</span><select value={value} onChange={(event) => onChange(event.target.value as TeacherReadiness | 'all')}><option value="all">Все статусы</option>{Object.entries(readinessSemantics).map(([status, meta]) => <option value={status} key={status}>{meta.label}</option>)}</select></label>;
}

type ProgramViewRow = UniversityProgramRow & {
  externalApplication?: ExternalApplication;
};

function ProgramRow({ row }: { row: ProgramViewRow }) {
  return <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.id.split('-').at(-1) ? `Программа ${row.id.split('-').at(-1)}` : 'Программа'}</span></>;
}

function SyncMeta({ source, syncedAt }: { source: 'LMS' | 'Сайт' | 'Ручные данные'; syncedAt: string | null }) {
  return <div className={styles.integrationMeta}><StatusBadge data-testid={source === 'LMS' ? 'external-badge' : undefined} intent={source === 'Ручные данные' ? 'neutral' : 'brand'}>{source}</StatusBadge><Tooltip content={<span>{syncedAt ? formatDateTimeRu(syncedAt) : 'Дата синхронизации недоступна'}</span>}><time data-testid="sync-date" dateTime={syncedAt ?? undefined}>Синхронизировано: {syncedAt ? formatDate(syncedAt) : 'недоступно'}</time></Tooltip></div>;
}

function demandLabel(score: number | null): string {
  if (score === null) return 'Нет данных';
  if (score >= 75) return `Высокий (${score}/100)`;
  if (score >= 45) return `Средний (${score}/100)`;
  return `Низкий (${score}/100)`;
}

function ExternalUnavailableNotice({ source, error }: { source: 'LMS' | 'сайта'; error: unknown }) {
  const normalized = normalizeApiError(error);
  return <p className={styles.externalNotice} role="status">{isExternalSourceUnavailable(error) ? `Источник ${source} временно недоступен.` : normalized.message} Показаны доступные данные.</p>;
}

function ProgramsSection({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [statusFilter, setStatusFilter] = useState<ProgramStatus | 'all'>('all');
  const [toast, setToast] = useState<{ intent: 'success' | 'error' | 'info'; title: string; message?: ReactNode } | null>(null);
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: universityProgramsQueryKey(id), queryFn: () => getUniversityPrograms(id), staleTime: 30_000 });
  const websiteQuery = useQuery({ queryKey: universityExternalDataQueryKey(id, 'website'), queryFn: () => getUniversityExternalData(id, 'website'), staleTime: 30_000 });
  const createMutation = useMutation({
    mutationFn: (externalId: string) => createWorkflowFromExternal({ universityId: id, source: 'website', externalId }),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: universityExternalDataQueryKey(id, 'website') }),
        queryClient.invalidateQueries({ queryKey: universityProgramsQueryKey(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflow(result.instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.overview }),
      ]);
      const next = new URLSearchParams(searchParams.toString());
      next.set('tab', 'workflow');
      next.set('program', result.externalId);
      next.set('workflow', result.instanceId);
      router.push(`${pathname}?${next.toString()}`, { scroll: false });
    },
    onError: (error) => setToast({ intent: 'error', title: 'Workflow не создан', message: normalizeApiError(error).message }),
  });
  const rows = useMemo<ProgramViewRow[]>(() => {
    const base = query.data ?? [];
    const applications = websiteQuery.data?.applications ?? [];
    const byName = new Map(applications.map((application) => [application.programName.toLocaleLowerCase('ru-RU'), application]));
    const merged = base.map((row) => ({ ...row, externalApplication: byName.get(row.name.toLocaleLowerCase('ru-RU')) }));
    const existingNames = new Set(base.map((row) => row.name.toLocaleLowerCase('ru-RU')));
    applications.filter((application) => !existingNames.has(application.programName.toLocaleLowerCase('ru-RU'))).forEach((application) => {
      merged.push({ id: `external-${application.id}`, direction: 'Данные с сайта', name: application.programName, status: 'planned', launchDate: '', responsible: null, teachersCount: 0, studentsCount: 0, externalApplication: application });
    });
    return merged.filter((row) => statusFilter === 'all' || row.status === statusFilter);
  }, [query.data, statusFilter, websiteQuery.data]);
  const columns: PassportTableColumn<ProgramViewRow>[] = [
    { id: 'direction', label: 'Направление', sortable: true, sortValue: (row) => row.direction, render: (row) => row.direction },
    { id: 'name', label: 'Программа', sortable: true, sortValue: (row) => row.name, render: (row) => <ProgramRow row={row} /> },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => programStatusLabels[row.status], render: (row) => <ProgramStatusBadge status={row.status} /> },
    { id: 'launchDate', label: 'Дата запуска', sortable: true, sortValue: (row) => row.launchDate, render: (row) => formatDate(row.launchDate) },
    { id: 'responsible', label: 'Ответственный', sortable: true, sortValue: (row) => row.responsible?.name ?? '', render: (row) => row.responsible?.name ?? 'Не назначен' },
    { id: 'applications', label: 'Заявки с сайта', sortable: true, sortValue: (row) => row.externalApplication?.applicationsCount ?? 0, render: (row) => row.externalApplication?.applicationsCount ?? '—' },
    { id: 'demand', label: 'Спрос', sortable: true, sortValue: (row) => row.externalApplication?.demandScore ?? -1, render: (row) => demandLabel(row.externalApplication?.demandScore ?? null) },
    { id: 'source', label: 'Источник', render: (row) => row.externalApplication ? <StatusBadge intent="brand">Сайт</StatusBadge> : <StatusBadge intent="neutral">Ручные данные</StatusBadge> },
    { id: 'sync', label: 'Синхронизация', render: (row) => row.externalApplication ? <time dateTime={row.externalApplication.syncedAt ?? undefined}>{row.externalApplication.syncedAt ? formatDate(row.externalApplication.syncedAt) : '—'}</time> : '—' },
    { id: 'actions', label: 'Действия', render: (row) => row.externalApplication ? <Button data-testid="create-workflow-from-external" variant="primary" size="s" type="button" loading={createMutation.isPending && createMutation.variables === row.externalApplication.id} disabled={createMutation.isPending} onClick={() => createMutation.mutate(row.externalApplication?.id ?? '')}>Создать Workflow</Button> : <Button variant="ghost" size="s" type="button" disabled title="Детали программы появятся после подключения маршрута">Открыть</Button> },
  ];
  const mobileFields: PassportMobileField<ProgramViewRow>[] = [
    { label: 'Программа', render: (row) => <ProgramRow row={row} /> },
    { label: 'Направление', render: (row) => row.direction },
    { label: 'Статус', render: (row) => <ProgramStatusBadge status={row.status} /> },
    { label: 'Заявки с сайта', render: (row) => row.externalApplication?.applicationsCount ?? '—' },
    { label: 'Спрос', render: (row) => demandLabel(row.externalApplication?.demandScore ?? null) },
    { label: 'Источник', render: (row) => row.externalApplication ? <StatusBadge intent="brand">Сайт</StatusBadge> : <StatusBadge intent="neutral">Ручные данные</StatusBadge> },
    { label: 'Синхронизация', render: (row) => row.externalApplication?.syncedAt ? formatDate(row.externalApplication.syncedAt) : '—' },
    { label: 'Действия', render: (row) => row.externalApplication ? <Button data-testid="create-workflow-from-external" variant="primary" size="s" type="button" loading={createMutation.isPending && createMutation.variables === row.externalApplication.id} disabled={createMutation.isPending} onClick={() => createMutation.mutate(row.externalApplication?.id ?? '')}>Создать Workflow</Button> : null },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Программы"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  const externalToast = websiteQuery.isError ? <div className={styles.toastViewport}><Toast intent="error" title="Источник сайта недоступен" message="Показаны доступные локальные данные." /></div> : null;
  return <section className={styles.section} aria-label="Программы"><SectionToolbar title="Программы"><div className={styles.integrationControls}>{websiteQuery.data ? <SyncMeta source="Сайт" syncedAt={websiteQuery.data.syncedAt} /> : <StatusBadge intent="neutral">Ручные данные</StatusBadge>}<ProgramFilter value={statusFilter} onChange={setStatusFilter} /></div></SectionToolbar>{websiteQuery.isError ? <ExternalUnavailableNotice source="сайта" error={websiteQuery.error} /> : null}<PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет программ с выбранным статусом" />{toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : externalToast}</section>;
}

function ProgramChips({ programs }: { programs: string[] }) {
  const visible = programs.slice(0, 2);
  const remaining = programs.length - visible.length;
  return <div className={styles.chips} aria-label={`Разрешённые программы: ${programs.join(', ')}`}>{visible.map((program) => <span className={styles.chip} key={program}>{program}</span>)}{remaining > 0 ? <span className={styles.chipMore}>+{remaining}</span> : null}</div>;
}

function TeachersSection({ id }: { id: string }) {
  const [readinessFilter, setReadinessFilter] = useState<TeacherReadiness | 'all'>('all');
  const query = useQuery({ queryKey: universityTeachersQueryKey(id), queryFn: () => getUniversityTeachers(id), staleTime: 30_000 });
  const rows = useMemo(() => (query.data?.filter((row) => readinessFilter === 'all' || row.readiness === readinessFilter) ?? []).sort((left, right) => ({ expired: 0, attention: 1, ready: 2 }[left.readiness] - { expired: 0, attention: 1, ready: 2 }[right.readiness])), [query.data, readinessFilter]);
  const columns: PassportTableColumn<UniversityTeacherRow>[] = [
    { id: 'name', label: 'ФИО', sortable: true, sortValue: (row) => row.name, render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'position', label: 'Должность', sortable: true, sortValue: (row) => row.position, render: (row) => row.position },
    { id: 'readiness', label: 'Готовность', sortable: true, sortValue: (row) => ({ expired: 0, attention: 1, ready: 2 }[row.readiness]), render: (row) => <ReadinessBadge readiness={row.readiness} size="sm" /> },
    { id: 'training', label: 'Следующее обучение', sortable: true, sortValue: (row) => row.nextTrainingDate ?? '', render: (row) => row.nextTrainingDate ? formatDate(row.nextTrainingDate) : 'Данные отсутствуют' },
    { id: 'programs', label: 'Программы', render: (row) => <ProgramChips programs={row.allowedPrograms} /> },
    { id: 'actions', label: 'Действия', render: (row) => <Link className={styles.actionLink} href={`/teachers/${row.id}`}>Открыть</Link> },
  ];
  const mobileFields: PassportMobileField<UniversityTeacherRow>[] = [
    { label: 'ФИО', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { label: 'Должность', render: (row) => row.position },
    { label: 'Готовность', render: (row) => <ReadinessBadge readiness={row.readiness} size="md" /> },
    { label: 'Обучение', render: (row) => row.nextTrainingDate ? formatDate(row.nextTrainingDate) : 'Данные отсутствуют' },
    { label: 'Программы', render: (row) => <ProgramChips programs={row.allowedPrograms} /> },
    { label: 'Действия', render: (row) => <Link className={styles.actionLink} href={`/teachers/${row.id}`}>Открыть профиль</Link> },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Преподаватели"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-label="Преподаватели"><SectionToolbar title="Преподаватели"><TeacherFilter value={readinessFilter} onChange={setReadinessFilter} /></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет преподавателей с выбранным статусом" /></section>;
}

function StudentSummary({ total, active, graduated, academicLeave }: { total: number; active: number; graduated: number; academicLeave: number }) {
  const metrics = [['Всего', total], ['Активные', active], ['Выпущены', graduated], ['Академический отпуск', academicLeave]] as const;
  return <div className={styles.studentSummary} aria-label="Сводка по студентам">{metrics.map(([label, value]) => <MetricCard label={label} value={value} centered key={label} />)}</div>;
}

type StudentViewRow = UniversityStudentsByProgram & {
  id: string;
  studentName?: string;
  flow: string | null;
  progress: number | null;
  source: 'lms' | 'manual';
  syncedAt: string | null;
};

function StudentRowName({ row }: { row: StudentViewRow }) {
  return <><strong className={styles.primaryCell}>{row.studentName ?? row.programName}</strong>{row.studentName ? <span className={styles.secondaryCell}>{row.programName}</span> : null}</>;
}

function StudentsSection({ id }: { id: string }) {
  const query = useQuery({ queryKey: universityStudentsQueryKey(id), queryFn: () => getUniversityStudentsSummary(id), staleTime: 30_000 });
  const lmsQuery = useQuery({ queryKey: universityExternalDataQueryKey(id, 'lms'), queryFn: () => getUniversityExternalData(id, 'lms'), staleTime: 30_000 });
  const [toast, setToast] = useState<{ intent: 'success' | 'error' | 'info'; title: string; message?: ReactNode } | null>(null);
  const rows = useMemo<StudentViewRow[]>(() => {
    const external = lmsQuery.data?.students ?? [];
    if (external.length) return external.map((student: ExternalStudent) => ({ id: student.id, programId: student.id, studentName: student.name, programName: student.programName ?? 'Программа не указана', active: 1, graduated: 0, total: 1, flow: student.flow, progress: student.progress, source: 'lms' as const, syncedAt: student.syncedAt }));
    return (query.data?.byProgram ?? []).map((row) => ({ ...row, id: row.programId, flow: null, progress: null, source: 'manual' as const, syncedAt: null }));
  }, [lmsQuery.data, query.data]);
  const columns: PassportTableColumn<StudentViewRow>[] = [
    { id: 'programName', label: 'Студент / программа', sortable: true, sortValue: (row) => row.studentName ?? row.programName, render: (row) => <StudentRowName row={row} /> },
    { id: 'flow', label: 'Поток', sortable: true, sortValue: (row) => row.flow ?? '', render: (row) => row.flow ?? '—' },
    { id: 'progress', label: 'Прогресс', sortable: true, sortValue: (row) => row.progress ?? -1, render: (row) => row.progress === null ? '—' : `${row.progress}%` },
    { id: 'active', label: 'Активные', sortable: true, sortValue: (row) => row.active, render: (row) => row.active },
    { id: 'graduated', label: 'Выпущены', sortable: true, sortValue: (row) => row.graduated, render: (row) => row.graduated },
    { id: 'total', label: 'Всего', sortable: true, sortValue: (row) => row.total, render: (row) => row.total },
    { id: 'source', label: 'Источник', render: (row) => row.source === 'lms' ? <StatusBadge intent="brand">LMS</StatusBadge> : <StatusBadge intent="neutral">Ручные данные</StatusBadge> },
    { id: 'syncedAt', label: 'Синхронизация', render: (row) => row.syncedAt ? formatDate(row.syncedAt) : '—' },
  ];
  const mobileFields: PassportMobileField<StudentViewRow>[] = [
    { label: 'Студент / программа', render: (row) => <StudentRowName row={row} /> },
    { label: 'Поток', render: (row) => row.flow ?? '—' },
    { label: 'Прогресс', render: (row) => row.progress === null ? '—' : `${row.progress}%` },
    { label: 'Состав', render: (row) => `${row.active} активных · ${row.graduated} выпущены · ${row.total} всего` },
    { label: 'Источник', render: (row) => row.source === 'lms' ? <StatusBadge intent="brand">LMS</StatusBadge> : <StatusBadge intent="neutral">Ручные данные</StatusBadge> },
    { label: 'Синхронизация', render: (row) => row.syncedAt ? formatDate(row.syncedAt) : '—' },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Студенты"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  const syncedAt = lmsQuery.data?.syncedAt ?? rows.find((row) => row.syncedAt)?.syncedAt ?? null;
  const summary = lmsQuery.data ? { total: rows.length, active: rows.length, graduated: 0, academicLeave: query.data.academicLeave } : query.data;
  const externalToast = lmsQuery.isError ? <div className={styles.toastViewport}><Toast intent="error" title="LMS недоступна" message="Показаны доступные локальные данные." /></div> : null;
  return <div className={styles.studentPage}><StudentSummary total={summary.total} active={summary.active} graduated={summary.graduated} academicLeave={summary.academicLeave} /><section className={styles.section} aria-label="Студенты по программам"><SectionToolbar title="Студенты"><SyncMeta source={lmsQuery.data ? 'LMS' : 'Ручные данные'} syncedAt={syncedAt} /></SectionToolbar>{lmsQuery.isError ? <ExternalUnavailableNotice source="LMS" error={lmsQuery.error} /> : null}<PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет данных по студентам" /></section>{toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : externalToast}</div>;
}

function ProductLicense({ row }: { row: UniversityProductRow }) {
  return <div className={styles.license}><strong>{row.licenseNumber}</strong><span>{formatDate(row.expiresAt)}</span></div>;
}

function ProductsSection({ id }: { id: string }) {
  const query = useQuery({ queryKey: universityProductsQueryKey(id), queryFn: () => getUniversityProducts(id), staleTime: 30_000 });
  const columns: PassportTableColumn<UniversityProductRow>[] = [
    { id: 'name', label: 'Продукт', sortable: true, sortValue: (row) => row.name, render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.version}</span></> },
    { id: 'vendor', label: 'Поставщик', sortable: true, sortValue: (row) => row.vendor, render: (row) => row.vendor },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => productStatusLabels[row.status], render: (row) => <ProductStatusBadge status={row.status} /> },
    { id: 'license', label: 'Лицензия', sortable: true, sortValue: (row) => row.expiresAt, render: (row) => <ProductLicense row={row} /> },
    { id: 'actions', label: 'Действия', render: () => <Button variant="ghost" size="s" type="button" disabled title="Карточка продукта появится после подключения маршрута">Просмотреть</Button> },
  ];
  const mobileFields: PassportMobileField<UniversityProductRow>[] = [
    { label: 'Продукт', render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.version}</span></> },
    { label: 'Поставщик', render: (row) => row.vendor },
    { label: 'Статус', render: (row) => <ProductStatusBadge status={row.status} /> },
    { label: 'Лицензия', render: (row) => <ProductLicense row={row} /> },
    { label: 'Действия', render: () => <Button variant="ghost" size="s" type="button" disabled title="Карточка продукта появится после подключения маршрута">Просмотреть</Button> },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Продукты"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-label="Продукты"><PassportDataTable rows={query.data} columns={columns} mobileFields={mobileFields} emptyMessage="Нет подключённых продуктов" /></section>;
}

export { ProgramsSection, ProductsSection, StudentsSection, TeachersSection };

const licenseStatusLabels: Record<UniversityLicenseStatus, string> = { active: 'Действует', expires_soon: 'Скоро истекает', expired: 'Просрочена' };
const documentStatusLabels: Record<UniversityDocumentStatus, string> = { signed: 'Подписан', pending: 'На подписи', expired: 'Просрочен' };
const meetingTypeLabels: Record<UniversityMeetingType, string> = { online: 'Онлайн', offline: 'Очно', phone: 'Телефон', email: 'Email' };

function LicenseStatusBadge({ status }: { status: UniversityLicenseStatus }) {
  return <StatusBadge intent={licenseStatusIntent[status]}>{licenseStatusLabels[status]}</StatusBadge>;
}

function DocumentStatusBadge({ status }: { status: UniversityDocumentStatus }) {
  return <StatusBadge intent={documentStatusIntent[status]}>{documentStatusLabels[status]}</StatusBadge>;
}

function LicensesSection({ id }: { id: string }) {
  const [statusFilter, setStatusFilter] = useState<UniversityLicenseStatus | 'all'>('all');
  const query = useQuery({ queryKey: universityLicensesQueryKey(id), queryFn: () => getUniversityLicenses(id), staleTime: 30_000 });
  const rows = useMemo(() => (query.data?.filter((row) => statusFilter === 'all' || row.status === statusFilter) ?? []).sort((left, right) => left.expiresAt.localeCompare(right.expiresAt)), [query.data, statusFilter]);
  const columns: PassportTableColumn<UniversityLicenseRow>[] = [
    { id: 'product', label: 'Продукт', sortable: true, sortValue: (row) => row.product, render: (row) => <strong className={styles.primaryCell}>{row.product}</strong> },
    { id: 'vendor', label: 'Вендор', sortable: true, sortValue: (row) => row.vendor, render: (row) => row.vendor },
    { id: 'licenseNumber', label: '№ лицензии', render: (row) => row.licenseNumber },
    { id: 'signedAt', label: 'Подписана', sortable: true, sortValue: (row) => row.signedAt, render: (row) => formatDate(row.signedAt) },
    { id: 'expiresAt', label: 'Истекает', sortable: true, sortValue: (row) => row.expiresAt, render: (row) => formatDate(row.expiresAt) },
    { id: 'status', label: 'Статус', render: (row) => <LicenseStatusBadge status={row.status} /> },
    { id: 'transfer', label: 'Передача', render: (row) => row.transfer },
    { id: 'contract', label: 'Договор', render: (row) => <details className={styles.inlineDetails}><summary>Подробнее</summary><span>{row.contract}</span></details> },
  ];
  const mobileFields: PassportMobileField<UniversityLicenseRow>[] = [
    { label: 'Продукт', render: (row) => <strong className={styles.primaryCell}>{row.product}</strong> },
    { label: 'Вендор', render: (row) => row.vendor },
    { label: 'Лицензия', render: (row) => row.licenseNumber },
    { label: 'Истекает', render: (row) => formatDate(row.expiresAt) },
    { label: 'Статус', render: (row) => <LicenseStatusBadge status={row.status} /> },
    { label: 'Договор', render: (row) => <details className={styles.inlineDetails}><summary>Подробнее</summary><span>{row.contract}</span></details> },
  ];
  if (query.isPending) return <section className={styles.section} aria-label="Лицензии"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Лицензии"><SectionToolbar title="Лицензии"><label className={styles.filter}><span>Статус</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UniversityLicenseStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(licenseStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Лицензии пока не добавлены" /></section>;
}

function DocumentFile({ row }: { row: UniversityDocumentRow }) {
  return <div className={styles.fileCell}><DocumentText size={20} fill="currentColor" /><div><strong className={styles.primaryCell} title={row.fileName}>{row.fileName}</strong><span className={styles.secondaryCell}>{row.fileSize}</span></div></div>;
}

function DocumentsSection({ id }: { id: string }) {
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<UniversityDocumentStatus | 'all'>('all');
  const query = useQuery({ queryKey: universityDocumentsQueryKey(id), queryFn: () => getUniversityDocuments(id), staleTime: 30_000 });
  const types = useMemo(() => [...new Set(query.data?.map((row) => row.type) ?? [])], [query.data]);
  const rows = useMemo(() => (query.data?.filter((row) => (typeFilter === 'all' || row.type === typeFilter) && (statusFilter === 'all' || row.status === statusFilter)) ?? []).sort((left, right) => right.uploadedAt.localeCompare(left.uploadedAt)), [query.data, statusFilter, typeFilter]);
  const columns: PassportTableColumn<UniversityDocumentRow>[] = [
    { id: 'type', label: 'Тип', sortable: true, sortValue: (row) => row.type, render: (row) => row.type },
    { id: 'name', label: 'Название', sortable: true, sortValue: (row) => row.name, render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'file', label: 'Файл', render: (row) => <DocumentFile row={row} /> },
    { id: 'signedAt', label: 'Подписан', render: (row) => row.signedAt ? formatDate(row.signedAt) : 'Не подписан' },
    { id: 'expiresAt', label: 'Истекает', render: (row) => row.expiresAt ? formatDate(row.expiresAt) : '—' },
    { id: 'status', label: 'Статус', render: (row) => <DocumentStatusBadge status={row.status} /> },
    { id: 'uploadedBy', label: 'Загрузил', render: (row) => row.uploadedBy },
    { id: 'uploadedAt', label: 'Дата', sortable: true, sortValue: (row) => row.uploadedAt, render: (row) => formatDate(row.uploadedAt) },
    { id: 'download', label: 'Файл', render: (row) => row.downloadUrl ? <a className={styles.iconAction} href={row.downloadUrl} download aria-label={`Скачать ${row.fileName}`}><Download size={18} fill="currentColor" /></a> : <button className={styles.iconAction} type="button" disabled aria-label={`Скачивание ${row.fileName} станет доступно после подключения API`}><Download size={18} fill="currentColor" /></button> },
  ];
  const mobileFields: PassportMobileField<UniversityDocumentRow>[] = [
    { label: 'Документ', render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.type}</span></> },
    { label: 'Файл', render: (row) => <DocumentFile row={row} /> },
    { label: 'Статус', render: (row) => <DocumentStatusBadge status={row.status} /> },
    { label: 'Дата', render: (row) => formatDate(row.uploadedAt) },
    { label: 'Скачать', render: (row) => row.downloadUrl ? <a className={styles.iconAction} href={row.downloadUrl} download aria-label={`Скачать ${row.fileName}`}><Download size={18} fill="currentColor" /></a> : <button className={styles.iconAction} type="button" disabled aria-label="Скачивание станет доступно после подключения API"><Download size={18} fill="currentColor" /></button> },
  ];
  if (query.isPending) return <section className={styles.section} aria-label="Документы"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Документы"><SectionToolbar title="Документы"><div className={styles.filtersRow}><label className={styles.filter}><span>Тип</span><select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="all">Все типы</option>{types.map((type) => <option value={type} key={type}>{type}</option>)}</select></label><label className={styles.filter}><span>Статус</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UniversityDocumentStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(documentStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Документы пока не добавлены" /></section>;
}

function MeetingParticipants({ participants }: { participants: UniversityMeetingRow['participants'] }) {
  return <div className={styles.participants} aria-label={`Участники: ${participants.map((participant) => participant.name).join(', ')}`}>{participants.slice(0, 3).map((participant) => <Avatar initials={participant.initials} size="s" key={participant.id} />)}{participants.length > 3 ? <span className={styles.participantMore}>+{participants.length - 3}</span> : null}</div>;
}

function MeetingsSection({ id, canAdd }: { id: string; canAdd: boolean }) {
  const query = useQuery({ queryKey: universityMeetingsQueryKey(id), queryFn: () => getUniversityMeetings(id), staleTime: 30_000 });
  if (query.isPending) return <section className={styles.section} aria-label="Встречи"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  return <section className={`${styles.section} ${styles.meetingSurface}`} aria-label="Встречи">{canAdd ? <SectionToolbar title="Встречи"><Button variant="primary" size="s" type="button" disabled title="Создание встречи подключится после появления API"><Calendar size={16} fill="currentColor" />Добавить встречу</Button></SectionToolbar> : <h2 className={styles.meetingTitle}>Встречи</h2>}{query.data.length ? <ol className={styles.meetingTimeline}>{query.data.slice().sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)).map((meeting) => <li className={styles.meetingItem} key={meeting.id}><div className={styles.meetingMarker} aria-hidden="true" /><article className={styles.meetingContent}><div className={styles.meetingMeta}><time dateTime={meeting.occurredAt}>{formatDateTimeRu(meeting.occurredAt)}</time><span className={styles.meetingType}>{meetingTypeLabels[meeting.type]}</span></div><h3>{meeting.subject}</h3><MeetingParticipants participants={meeting.participants} /><details className={styles.meetingDetails}><summary>Итог и следующее действие</summary><p><strong>Итог:</strong> {meeting.outcome}</p><p><strong>Следующее действие:</strong> {meeting.nextAction}{meeting.dueDate ? ` до ${formatDateRu(meeting.dueDate)}` : ''}</p></details><span className={styles.meetingAuthor}>Автор: {meeting.author}</span></article></li>)}</ol> : <EmptyState icon={<Calendar size={20} fill="currentColor" />} title="Встреч пока нет" description="Записи появятся здесь после первого взаимодействия." headingLevel={3} />}</section>;
}

function ResponsibleAssignmentDrawer({ id, currentName, onClose, onSuccess }: { id: string; currentName: string; onClose: () => void; onSuccess: () => void }) {
  const queryClient = useQueryClient();
  const candidatesQuery = useQuery({ queryKey: adminUsersQueryKeys.responsibleCandidates, queryFn: listResponsibleCandidates, staleTime: 30_000 });
  const [candidateId, setCandidateId] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const candidates = candidatesQuery.data ?? [];
  const selectedId = candidateId || candidates[0]?.id || '';
  const mutation = useMutation({
    mutationFn: () => assignUniversityResponsible({ universityId: id, responsibleId: selectedId, reason: reason.trim() }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: universityPassportQueryKey(id) });
      void queryClient.invalidateQueries({ queryKey: universityResponsiblesQueryKey(id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.universities.historyFamily(id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.universities.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.audit.all });
      onSuccess();
    },
    onError: (cause) => setError(normalizeApiError(cause, { fallbackMessage: 'Не удалось сменить ответственного.' }).message),
  });

  return <Drawer title="Сменить ответственного" onClose={() => { if (!mutation.isPending) onClose(); }}><div className={styles.assignmentForm}><p className={styles.assignmentIntro}><strong>Текущий ответственный:</strong> {currentName}<br />Выберите пользователя из допустимых кандидатов. Изменение попадёт в паспорт ВУЗа и журнал аудита после ответа сервера.</p>{candidatesQuery.isPending ? <p className={styles.emptySection}>Загрузка кандидатов…</p> : candidatesQuery.isError ? <RouteErrorState compact onRetry={() => void candidatesQuery.refetch()} /> : <label className={styles.filter}><span>Новый ответственный</span><Select value={selectedId} onChange={(event) => setCandidateId(event.target.value)}><option value="" disabled>Выберите пользователя</option>{candidates.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.name} · {candidate.role}</option>)}</Select></label>}<label className={styles.filter}><span>Причина</span><TextArea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Например, перераспределение зоны ответственности" rows={4} /></label>{error ? <p className={styles.assignmentError} role="alert">{error}</p> : null}<div className={styles.assignmentActions}><Button variant="ghost" type="button" disabled={mutation.isPending} onClick={onClose}>Отмена</Button><Button variant="primary" type="button" loading={mutation.isPending} disabled={mutation.isPending || !selectedId || !reason.trim() || candidatesQuery.isError} onClick={() => { setError(null); mutation.mutate(); }}>Сохранить</Button></div></div></Drawer>;
}

function ResponsiblesSection({ id, canEdit }: { id: string; canEdit: boolean }) {
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const [toast, setToast] = useState(false);
  const query = useQuery({ queryKey: universityResponsiblesQueryKey(id), queryFn: () => getUniversityResponsibles(id), staleTime: 30_000 });
  if (query.isPending) return <section className={styles.section} aria-label="Ответственные"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  const currentName = query.data.find((person) => person.isPrimary)?.name ?? 'Не назначен';
  return <><section className={styles.section} aria-label="Ответственные">{canEdit ? <SectionToolbar title="Ответственные"><Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Сменить ответственного</Button></SectionToolbar> : null}{query.data.length ? <div className={styles.responsiblesGrid}>{query.data.map((person) => <article className={styles.responsibleCard} key={person.id}><Avatar initials={person.initials} size="m" /><div className={styles.responsibleInfo}><h3>{person.name}</h3><p>{person.role}</p><a href={`mailto:${person.email}`}><Mail size={16} fill="currentColor" />{person.email}</a><a href={`tel:${person.phone.replace(/[^+\d]/g, '')}`}><Phone size={16} fill="currentColor" />{person.phone}</a></div>{person.isPrimary ? <StatusBadge intent="brand">Основной</StatusBadge> : null}</article>)}</div> : <EmptyState icon={<Mail size={20} fill="currentColor" />} title="Ответственные не назначены" description="Контактные лица появятся здесь после назначения." headingLevel={3} />}</section>{assignmentOpen ? <ResponsibleAssignmentDrawer id={id} currentName={currentName} onClose={() => setAssignmentOpen(false)} onSuccess={() => { setAssignmentOpen(false); setToast(true); }} /> : null}{toast ? <Toast intent="success" title="Ответственный изменён" message="Паспорт, история и связанные списки обновляются." onClose={() => setToast(false)} /> : null}</>;
}

export { LicensesSection, DocumentsSection, MeetingsSection, ResponsiblesSection };
