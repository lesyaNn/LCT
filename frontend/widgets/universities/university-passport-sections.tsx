'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useMemo, useState, type ReactNode } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Download from '@atomaro/icons/24/action/Download';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import Mail from '@atomaro/icons/24/communication/Mail';
import Phone from '@atomaro/icons/24/technology/Phone';
import { Button } from '@/shared/ui/rtk/button';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { Modal } from '@/shared/ui/rtk/modal';
import { EmptyState } from '@/shared/ui/empty-state';
import { Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { MetricCard } from '@/shared/ui/rtk/metric-card';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { BackgroundRefreshNotice } from '@/shared/ui/background-refresh-notice';
import { Toast } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { adminUsersQueryKeys, assignUniversityResponsible, listResponsibleCandidates } from '@/shared/lib/users-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import {
  createWorkflowFromExternal,
  externalSourceLabel,
  getUniversityExternalData,
  isExternalSourceUnavailable,
  normalizeStudentRows,
  universityExternalDataQueryKey,
  type ExternalApplication,
} from '@/shared/lib/external-integrations-repository';
import { documentStatusIntent, licenseStatusIntent, productStatusIntent, programStatusIntent, readinessSemantics } from '@/shared/lib/status-semantics';
import {
  getUniversityProducts,
  getUniversityPrograms,
  getUniversityLicenses,
  getUniversityDocuments,
  getUniversityMeetings,
  deleteUniversityMeeting,
  getUniversityResponsibles,
  getUniversityStudentsSummary,
  getUniversityStudents,
  deleteUniversityStudent,
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
  universityStudentsSummaryQueryKey,
  universityTeachersQueryKey,
  type ProgramStatus,
  type TeacherReadiness,
  type UniversityProductRow,
  type UniversityProductStatus,
  type UniversityProgramRow,
  type UniversityStudentsByProgram,
  type UniversityStudentListRow,
  type UniversityTeacherRow,
  type UniversityLicenseRow,
  type UniversityLicenseStatus,
  type UniversityDocumentRow,
  type UniversityDocumentStatus,
  type UniversityMeetingRow,
  type UniversityMeetingType,
  UNIVERSITY_PASSPORT_CAPABILITIES,
} from '@/shared/lib/universities-repository';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from './passport-data-table';
import { MeetingMutationForm, ProductAssignmentForm, ProgramAssignmentForm, StudentMutationForm } from './passport-mutation-forms';
import { ReadinessBadge } from '@/shared/ui/rtk/readiness-badge';
import styles from './university-passport-sections.module.css';

const formatDate = formatDateRu;

function SectionToolbar({ title, children }: { title?: string; children?: ReactNode }) {
  return <div className={styles.sectionToolbar}>{title ? <h2>{title}</h2> : null}{children ? <div className={styles.toolbarControls}>{children}</div> : null}</div>;
}

const productStatusLabels: Record<UniversityProductStatus, string> = {
  planned: 'Запланирован',
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
  return <label className={styles.filter}><span>Статус</span><Select value={value} onChange={(event) => onChange(event.target.value as ProgramStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(programStatusLabels).map(([status, label]) => <option value={status} key={status}>{label}</option>)}</Select></label>;
}

function TeacherFilter({ value, onChange }: { value: TeacherReadiness | 'all'; onChange: (value: TeacherReadiness | 'all') => void }) {
  return <label className={styles.filter}><span>Готовность</span><Select value={value} onChange={(event) => onChange(event.target.value as TeacherReadiness | 'all')}><option value="all">Все статусы</option>{Object.entries(readinessSemantics).map(([status, meta]) => <option value={status} key={status}>{meta.label}</option>)}</Select></label>;
}

type ProgramViewRow = UniversityProgramRow & {
  externalApplication?: ExternalApplication;
};

function ProgramRow({ row }: { row: ProgramViewRow }) {
  return <strong className={styles.primaryCell}>{row.name}</strong>;
}

function SyncMeta({ source, syncedAt, mode }: { source: 'LMS' | 'Сайт' | 'Ручные данные'; syncedAt: string | null; mode?: 'real' | 'mock' | 'import' | 'unconfigured' }) {
  if (mode === 'unconfigured') return <StatusBadge intent="neutral">Данные сайта не подключены</StatusBadge>;
  return <div className={styles.integrationMeta}><StatusBadge data-testid={source === 'LMS' ? 'external-badge' : undefined} intent={source === 'Ручные данные' ? 'neutral' : 'brand'}>{source}{mode === 'mock' ? ' · тест' : mode === 'import' ? ' · импорт' : ''}</StatusBadge><Tooltip content={<span>{syncedAt ? formatDateTimeRu(syncedAt) : 'Дата синхронизации недоступна'}</span>}><time data-testid="sync-date" dateTime={syncedAt ?? undefined}>Синхронизировано: {syncedAt ? formatDate(syncedAt) : 'недоступно'}</time></Tooltip></div>;
}

function demandLabel(score: number | null): string {
  if (score === null) return 'Нет данных';
  if (score >= 75) return `Высокий (${score}/100)`;
  if (score >= 45) return `Средний (${score}/100)`;
  return `Низкий (${score}/100)`;
}

function ExternalUnavailableNotice({ source, error, onRetry }: { source: 'LMS' | 'сайта'; error: unknown; onRetry: () => void }) {
  const normalized = normalizeApiError(error);
  return <div className={styles.externalNotice} role="status">{isExternalSourceUnavailable(error) ? `Источник ${source} временно недоступен.` : normalized.message} Показаны доступные данные. <Button variant="ghost" size="s" type="button" onClick={onRetry}>Повторить</Button></div>;
}

function ProgramsSection({ id }: { id: string }) {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const statusParam = searchParams.get('program_status');
  const statusFilter: ProgramStatus | 'all' = statusParam && statusParam in programStatusLabels ? statusParam as ProgramStatus : 'all';
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<{ intent: 'success' | 'error' | 'info'; title: string; message?: ReactNode } | null>(null);
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const changeStatusFilter = (value: ProgramStatus | 'all') => {
    const next = new URLSearchParams(searchParams.toString());
    if (value === 'all') next.delete('program_status'); else next.set('program_status', value);
    setPage(1);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  const canAttach = !isMockDataSourceFor('passport') && hasPermission(user, 'university.edit');
  const canCreateWorkflow = hasPermission(user, 'workflow.change_status');
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: universityProgramsQueryKey(id, page, 20, statusFilter), queryFn: ({ signal }) => getUniversityPrograms(id, page, 20, signal, statusFilter), placeholderData: keepPreviousData, staleTime: 30_000 });
  const websiteQuery = useQuery({ queryKey: universityExternalDataQueryKey(id, 'website'), queryFn: () => getUniversityExternalData(id, 'website'), enabled: UNIVERSITY_PASSPORT_CAPABILITIES.externalData, staleTime: 30_000 });
  const createMutation = useMutation({
    mutationFn: (externalId: string) => createWorkflowFromExternal({ universityId: id, source: 'website', externalId }),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: universityExternalDataQueryKey(id, 'website') }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.programsAll }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflow(result.instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.overview }),
      ]);
      const next = new URLSearchParams(searchParams.toString());
      next.set('tab', 'workflow');
      if (result.programId) next.set('program', result.programId);
      next.set('workflow', result.instanceId);
      router.push(`${pathname}?${next.toString()}`, { scroll: false });
    },
    onError: (error) => setToast({ intent: 'error', title: 'Workflow не создан', message: normalizeApiError(error).message }),
  });
  const openWorkflow = (application: ExternalApplication) => {
    if (!application.workflowInstanceId || !application.programId) return;
    const next = new URLSearchParams(searchParams.toString());
    next.set('tab', 'workflow');
    next.set('program', application.programId);
    next.set('workflow', application.workflowInstanceId);
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  };
  const applicationAction = (application: ExternalApplication) => application.workflowInstanceId
    ? <Button variant="ghost" size="s" type="button" onClick={() => openWorkflow(application)}>Перейти в Workflow</Button>
    : <Button data-testid="create-workflow-from-external" variant="primary" size="s" type="button" loading={createMutation.isPending && createMutation.variables === application.id} disabled={createMutation.isPending || !canCreateWorkflow} onClick={() => createMutation.mutate(application.id)}>Создать Workflow</Button>;
  const rows = useMemo<ProgramViewRow[]>(() => {
    const base = query.data?.items ?? [];
    const applications = websiteQuery.data?.applications ?? [];
    const byId = new Map(applications.filter((application) => application.programId).map((application) => [application.programId, application]));
    return base.map((row) => ({ ...row, externalApplication: byId.get(row.id) }));
  }, [query.data, websiteQuery.data]);
  const columns: PassportTableColumn<ProgramViewRow>[] = [
    { id: 'direction', label: 'Направление', sortable: true, sortValue: (row) => row.direction, render: (row) => row.direction },
    { id: 'name', label: 'Программа', sortable: true, sortValue: (row) => row.name, render: (row) => <ProgramRow row={row} /> },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => programStatusLabels[row.status], render: (row) => <ProgramStatusBadge status={row.status} /> },
    { id: 'launchDate', label: 'Дата запуска', sortable: true, sortValue: (row) => row.launchDate, render: (row) => formatDate(row.launchDate) },
    { id: 'responsible', label: 'Ответственный', sortable: true, sortValue: (row) => row.responsible?.name ?? '', render: (row) => row.responsible?.name ?? 'Не назначен' },
    { id: 'applications', label: 'Заявки с сайта', sortable: true, sortValue: (row) => row.externalApplication?.applicationsCount ?? 0, render: (row) => row.externalApplication?.applicationsCount ?? '—' },
    { id: 'demand', label: 'Спрос', sortable: true, sortValue: (row) => row.externalApplication?.demandScore ?? -1, render: (row) => demandLabel(row.externalApplication?.demandScore ?? null) },
    { id: 'source', label: 'Источник', render: (row) => row.externalApplication ? <StatusBadge intent="brand">{websiteQuery.data?.mode === 'import' ? 'Импорт' : 'Сайт'}</StatusBadge> : <StatusBadge intent="neutral">Ручные данные</StatusBadge> },
    { id: 'sync', label: 'Синхронизация', render: (row) => row.externalApplication ? <time dateTime={row.externalApplication.syncedAt ?? undefined}>{row.externalApplication.syncedAt ? formatDate(row.externalApplication.syncedAt) : '—'}</time> : '—' },
    { id: 'actions', label: 'Workflow', render: (row) => row.externalApplication ? applicationAction(row.externalApplication) : '—' },
  ];
  const mobileFields: PassportMobileField<ProgramViewRow>[] = [
    { label: 'Программа', render: (row) => <ProgramRow row={row} /> },
    { label: 'Направление', render: (row) => row.direction },
    { label: 'Статус', render: (row) => <ProgramStatusBadge status={row.status} /> },
    { label: 'Заявки с сайта', render: (row) => row.externalApplication?.applicationsCount ?? '—' },
    { label: 'Спрос', render: (row) => demandLabel(row.externalApplication?.demandScore ?? null) },
    { label: 'Источник', render: (row) => row.externalApplication ? <StatusBadge intent="brand">{websiteQuery.data?.mode === 'import' ? 'Импорт' : 'Сайт'}</StatusBadge> : <StatusBadge intent="neutral">Ручные данные</StatusBadge> },
    { label: 'Синхронизация', render: (row) => row.externalApplication?.syncedAt ? formatDate(row.externalApplication.syncedAt) : '—' },
    { label: 'Workflow', render: (row) => row.externalApplication ? applicationAction(row.externalApplication) : '—' },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Программы"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Программы"><SectionToolbar title="Программы"><div className={styles.integrationControls}>{websiteQuery.isError && isExternalSourceUnavailable(websiteQuery.error) ? <StatusBadge intent="neutral">Данные сайта сейчас недоступны</StatusBadge> : websiteQuery.data ? <SyncMeta source="Сайт" syncedAt={websiteQuery.data.syncedAt} mode={websiteQuery.data.mode} /> : <StatusBadge intent="neutral">Ручные данные</StatusBadge>}{canAttach ? <Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Добавить программу</Button> : null}</div></SectionToolbar><FilterToolbar embedded label="Фильтры программ" controls={() => <ProgramFilter value={statusFilter} onChange={changeStatusFilter} />} onReset={() => changeStatusFilter('all')} resetDisabled={statusFilter === 'all'} mobileCount={statusFilter === 'all' ? 0 : 1} />{websiteQuery.isError && !isExternalSourceUnavailable(websiteQuery.error) ? <ExternalUnavailableNotice source="сайта" error={websiteQuery.error} onRetry={() => void websiteQuery.refetch()} /> : null}<div className={styles.refreshStatus} aria-live="polite">{query.isFetching ? <span role="status">Обновляем программы…</span> : null}{query.isError ? <BackgroundRefreshNotice onRetry={() => void query.refetch()} /> : null}</div><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет программ с выбранным статусом" serverPagination={{ page, pageSize: 20, total: query.data.total, onPageChange: setPage }} />{assignmentOpen ? <ProgramAssignmentForm universityId={id} existingProgramIds={query.data.items.map((program) => program.id)} onClose={() => setAssignmentOpen(false)} onSaved={() => { setAssignmentOpen(false); setToast({ intent: 'success', title: 'Программа добавлена' }); }} /> : null}{toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : null}</section>;
}

function ProgramChips({ programs }: { programs: string[] }) {
  const visible = programs.slice(0, 2);
  const remaining = programs.length - visible.length;
  return <div className={styles.chips} aria-label={`Разрешённые программы: ${programs.join(', ')}`}>{visible.map((program) => <span className={styles.chip} key={program}>{program}</span>)}{remaining > 0 ? <span className={styles.chipMore}>+{remaining}</span> : null}</div>;
}

function TeachersSection({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const readinessParam = searchParams.get('teacher_readiness');
  const readinessFilter: TeacherReadiness | 'all' = readinessParam && readinessParam in readinessSemantics ? readinessParam as TeacherReadiness : 'all';
  const [page, setPage] = useState(1);
  const changeReadinessFilter = (value: TeacherReadiness | 'all') => {
    const next = new URLSearchParams(searchParams.toString());
    if (value === 'all') next.delete('teacher_readiness'); else next.set('teacher_readiness', value);
    setPage(1);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  const query = useQuery({ queryKey: universityTeachersQueryKey(id, page, 20, readinessFilter), queryFn: ({ signal }) => getUniversityTeachers(id, page, 20, signal, readinessFilter), placeholderData: keepPreviousData, staleTime: 30_000 });
  const rows = useMemo(() => [...(query.data?.items ?? [])].sort((left, right) => ({ expired: 0, attention: 1, ready: 2 }[left.readiness] - { expired: 0, attention: 1, ready: 2 }[right.readiness])), [query.data]);
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
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-label="Преподаватели"><SectionToolbar title="Преподаватели" /><FilterToolbar embedded label="Фильтры преподавателей" controls={() => <TeacherFilter value={readinessFilter} onChange={changeReadinessFilter} />} onReset={() => changeReadinessFilter('all')} resetDisabled={readinessFilter === 'all'} mobileCount={readinessFilter === 'all' ? 0 : 1} /><div className={styles.refreshStatus} aria-live="polite">{query.isFetching ? <span role="status">Обновляем преподавателей…</span> : null}{query.isError ? <BackgroundRefreshNotice onRetry={() => void query.refetch()} /> : null}</div><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет преподавателей с выбранным статусом" serverPagination={{ page, pageSize: 20, total: query.data.total, onPageChange: setPage }} /></section>;
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
  source: 'lms' | 'manual' | 'website' | 'import';
  syncedAt: string | null;
};

function StudentRowName({ row }: { row: StudentViewRow }) {
  return <><strong className={styles.primaryCell}>{row.studentName ?? row.programName}</strong>{row.studentName ? <span className={styles.secondaryCell}>{row.programName}</span> : null}</>;
}

function StudentsSection({ id }: { id: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState<UniversityStudentListRow | null | undefined>(undefined);
  const [deleteCandidate, setDeleteCandidate] = useState<UniversityStudentListRow | null>(null);
  const canWrite = !isMockDataSourceFor('passport') && hasPermission(user, 'university.edit');
  const query = useQuery({ queryKey: universityStudentsSummaryQueryKey(id), queryFn: () => getUniversityStudentsSummary(id, queryClient), staleTime: 30_000 });
  const listQuery = useQuery({ queryKey: universityStudentsQueryKey(id, page), queryFn: ({ signal }) => getUniversityStudents(id, page, 20, signal), placeholderData: keepPreviousData, staleTime: 30_000 });
  const lmsQuery = useQuery({ queryKey: universityExternalDataQueryKey(id, 'lms'), queryFn: () => getUniversityExternalData(id, 'lms'), enabled: UNIVERSITY_PASSPORT_CAPABILITIES.externalData, staleTime: 30_000 });
  const [toast, setToast] = useState<{ intent: 'success' | 'error' | 'info'; title: string; message?: ReactNode } | null>(null);
  const remove = useMutation({
    mutationFn: (studentId: string) => deleteUniversityStudent(studentId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.studentsFamily(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.passport(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.historyFamily(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.audit.all }),
      ]);
      setDeleteCandidate(null);
      setToast({ intent: 'success', title: 'Студент удалён' });
    },
    onError: (cause) => setToast({ intent: 'error', title: normalizeApiError(cause).message }),
  });
  const rows = useMemo<StudentViewRow[]>(() => {
    const programNames = new Map((query.data?.byProgram ?? []).map((item) => [item.programId, item.programName]));
    return normalizeStudentRows(listQuery.data?.items ?? [], lmsQuery.data?.students ?? []).map((row) => ({
      ...row, programName: programNames.get(row.programId) ?? row.programName,
    }));
  }, [lmsQuery.data, listQuery.data, query.data]);
  const columns: PassportTableColumn<StudentViewRow>[] = [
    { id: 'programName', label: 'Студент / программа', sortable: true, sortValue: (row) => row.studentName ?? row.programName, render: (row) => <StudentRowName row={row} /> },
    { id: 'flow', label: 'Поток', sortable: true, sortValue: (row) => row.flow ?? '', render: (row) => row.flow ?? '—' },
    { id: 'progress', label: 'Прогресс', sortable: true, sortValue: (row) => row.progress ?? -1, render: (row) => row.progress === null ? '—' : `${row.progress}%` },
    { id: 'active', label: 'Активные', sortable: true, sortValue: (row) => row.active, render: (row) => row.active },
    { id: 'graduated', label: 'Выпущены', sortable: true, sortValue: (row) => row.graduated, render: (row) => row.graduated },
    { id: 'total', label: 'Всего', sortable: true, sortValue: (row) => row.total, render: (row) => row.total },
    { id: 'source', label: 'Источник', render: (row) => <StatusBadge intent={row.source === 'manual' ? 'neutral' : 'brand'}>{externalSourceLabel(row.source)}</StatusBadge> },
    { id: 'syncedAt', label: 'Синхронизация', render: (row) => row.syncedAt ? formatDate(row.syncedAt) : '—' },
    { id: 'actions', label: 'Действия', render: (row) => canWrite ? <div className={styles.assignmentActions}><Button variant="ghost" size="s" type="button" onClick={() => setEditor(row)}>Изменить</Button><Button variant="ghost" size="s" type="button" onClick={() => setDeleteCandidate(row)}>Удалить</Button></div> : null },
  ];
  const mobileFields: PassportMobileField<StudentViewRow>[] = [
    { label: 'Студент / программа', render: (row) => <StudentRowName row={row} /> },
    { label: 'Поток', render: (row) => row.flow ?? '—' },
    { label: 'Прогресс', render: (row) => row.progress === null ? '—' : `${row.progress}%` },
    { label: 'Состав', render: (row) => `${row.active} активных · ${row.graduated} выпущены · ${row.total} всего` },
    { label: 'Источник', render: (row) => <StatusBadge intent={row.source === 'manual' ? 'neutral' : 'brand'}>{externalSourceLabel(row.source)}</StatusBadge> },
    { label: 'Синхронизация', render: (row) => row.syncedAt ? formatDate(row.syncedAt) : '—' },
    { label: 'Действия', render: (row) => canWrite ? <div className={styles.assignmentActions}><Button variant="ghost" size="s" type="button" onClick={() => setEditor(row)}>Изменить</Button><Button variant="ghost" size="s" type="button" onClick={() => setDeleteCandidate(row)}>Удалить</Button></div> : null },
  ];

  if (query.isPending || listQuery.isPending) return <section className={styles.section} aria-label="Студенты"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  if (!listQuery.data) return <RouteErrorState compact onRetry={() => void listQuery.refetch()} />;
  const syncedAt = lmsQuery.data?.syncedAt ?? rows.find((row) => row.syncedAt)?.syncedAt ?? null;
  const summary = query.data;
  const externalToast = lmsQuery.isError ? <div className={styles.toastViewport}><Toast intent="error" title="LMS недоступна" message="Показаны доступные локальные данные." /></div> : null;
  return <div className={styles.studentPage}><StudentSummary total={summary.total} active={summary.active} graduated={summary.graduated} academicLeave={summary.academicLeave} /><section className={styles.section} aria-label="Студенты по программам"><SectionToolbar title="Студенты"><div className={styles.toolbarControls}><SyncMeta source={lmsQuery.data ? 'LMS' : 'Ручные данные'} syncedAt={syncedAt} mode={lmsQuery.data?.mode} />{canWrite ? <Button variant="primary" size="s" type="button" onClick={() => setEditor(null)}>Добавить студента</Button> : null}</div></SectionToolbar>{lmsQuery.isError ? <ExternalUnavailableNotice source="LMS" error={lmsQuery.error} onRetry={() => void lmsQuery.refetch()} /> : null}<PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет данных по студентам" serverPagination={{ page, pageSize: 20, total: listQuery.data.total, onPageChange: setPage }} /></section>{editor !== undefined ? <StudentMutationForm universityId={id} student={editor} onClose={() => setEditor(undefined)} onSaved={() => { setEditor(undefined); setToast({ intent: 'success', title: 'Данные студента сохранены' }); }} /> : null}{deleteCandidate ? <Modal title="Удалить студента?" onClose={() => { if (!remove.isPending) setDeleteCandidate(null); }}><p>Студент «{deleteCandidate.studentName}» будет удалён без возможности восстановления.</p><div className={styles.assignmentActions}><Button variant="ghost" type="button" disabled={remove.isPending} onClick={() => setDeleteCandidate(null)}>Отмена</Button><Button variant="danger" type="button" loading={remove.isPending} disabled={remove.isPending} onClick={() => remove.mutate(deleteCandidate.id)}>Удалить</Button></div></Modal> : null}{toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : externalToast}</div>;
}

function ProductLicense({ row }: { row: UniversityProductRow }) {
  return <div className={styles.license}><strong>{row.licenseNumber}</strong><span>{formatDate(row.expiresAt)}</span></div>;
}

function ProductsSection({ id }: { id: string }) {
  const { user } = useAuth();
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const canAttach = !isMockDataSourceFor('passport') && hasPermission(user, 'university.edit');
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: universityProductsQueryKey(id), queryFn: () => getUniversityProducts(id, queryClient), staleTime: 30_000 });
  const columns: PassportTableColumn<UniversityProductRow>[] = [
    { id: 'name', label: 'Продукт', sortable: true, sortValue: (row) => row.name, render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.version}</span></> },
    { id: 'vendor', label: 'Поставщик', sortable: true, sortValue: (row) => row.vendor, render: (row) => row.vendor },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => productStatusLabels[row.status], render: (row) => <ProductStatusBadge status={row.status} /> },
    { id: 'license', label: 'Лицензия', sortable: true, sortValue: (row) => row.expiresAt, render: (row) => <ProductLicense row={row} /> },
  ];
  const mobileFields: PassportMobileField<UniversityProductRow>[] = [
    { label: 'Продукт', render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.version}</span></> },
    { label: 'Поставщик', render: (row) => row.vendor },
    { label: 'Статус', render: (row) => <ProductStatusBadge status={row.status} /> },
    { label: 'Лицензия', render: (row) => <ProductLicense row={row} /> },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Продукты"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-label="Продукты"><SectionToolbar title="Продукты">{canAttach ? <Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Добавить продукт</Button> : null}</SectionToolbar><PassportDataTable rows={query.data} columns={columns} mobileFields={mobileFields} emptyMessage="Нет подключённых продуктов" />{assignmentOpen ? <ProductAssignmentForm universityId={id} existingProductIds={query.data.map((product) => product.id)} onClose={() => setAssignmentOpen(false)} onSaved={() => { setAssignmentOpen(false); setSaved(true); }} /> : null}{saved ? <div className={styles.toastViewport}><Toast intent="success" title="Продукт добавлен" onClose={() => setSaved(false)} /></div> : null}</section>;
}

export { ProgramsSection, ProductsSection, StudentsSection, TeachersSection };

const licenseStatusLabels: Record<UniversityLicenseStatus, string> = { active: 'Действует', expires_soon: 'Скоро истекает', expired: 'Просрочена' };
const documentStatusLabels: Record<UniversityDocumentStatus, string> = { signed: 'Подписан', pending: 'На подписи', expired: 'Просрочен', archived: 'В архиве' };
const meetingTypeLabels: Record<UniversityMeetingType, string> = { online: 'Онлайн', offline: 'Очно', phone: 'Телефон', email: 'Email' };

function LicenseStatusBadge({ status }: { status: UniversityLicenseStatus }) {
  return <StatusBadge intent={licenseStatusIntent[status]}>{licenseStatusLabels[status]}</StatusBadge>;
}

function DocumentStatusBadge({ status }: { status: UniversityDocumentStatus }) {
  return <StatusBadge intent={documentStatusIntent[status]}>{documentStatusLabels[status]}</StatusBadge>;
}

function LicensesSection({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<UniversityLicenseStatus | 'all'>('all');
  const query = useQuery({ queryKey: universityLicensesQueryKey(id), queryFn: () => getUniversityLicenses(id, queryClient), staleTime: 30_000 });
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
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Лицензии"><SectionToolbar title="Лицензии"><label className={styles.filter}><span>Статус</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UniversityLicenseStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(licenseStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Лицензии пока не добавлены" /></section>;
}

function DocumentFile({ row }: { row: UniversityDocumentRow }) {
  return <div className={styles.fileCell}><DocumentText size={20} fill="currentColor" /><div><strong className={styles.primaryCell} title={row.fileName}>{row.fileName}</strong><span className={styles.secondaryCell}>{row.fileSize}</span></div></div>;
}

function DocumentsSection({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<UniversityDocumentStatus | 'all'>('all');
  const query = useQuery({ queryKey: universityDocumentsQueryKey(id), queryFn: () => getUniversityDocuments(id, queryClient), staleTime: 30_000 });
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
    { id: 'download', label: 'Файл', render: (row) => row.downloadUrl ? <a className={styles.iconAction} href={row.downloadUrl} download aria-label={`Скачать ${row.fileName}`}><Download size={18} fill="currentColor" /></a> : <span aria-label="Файл недоступен">—</span> },
  ];
  const mobileFields: PassportMobileField<UniversityDocumentRow>[] = [
    { label: 'Документ', render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.type}</span></> },
    { label: 'Файл', render: (row) => <DocumentFile row={row} /> },
    { label: 'Статус', render: (row) => <DocumentStatusBadge status={row.status} /> },
    { label: 'Дата', render: (row) => formatDate(row.uploadedAt) },
    { label: 'Скачать', render: (row) => row.downloadUrl ? <a className={styles.iconAction} href={row.downloadUrl} download aria-label={`Скачать ${row.fileName}`}><Download size={18} fill="currentColor" /></a> : <span aria-label="Файл недоступен">—</span> },
  ];
  if (query.isPending) return <section className={styles.section} aria-label="Документы"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Документы"><SectionToolbar title="Документы"><div className={styles.filtersRow}><label className={styles.filter}><span>Тип</span><select disabled={!UNIVERSITY_PASSPORT_CAPABILITIES.documentFilters} title={!UNIVERSITY_PASSPORT_CAPABILITIES.documentFilters ? "Backend пока не поддерживает фильтры документов" : undefined} value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="all">Все типы</option>{types.map((type) => <option value={type} key={type}>{type}</option>)}</select></label><label className={styles.filter}><span>Статус</span><select disabled={!UNIVERSITY_PASSPORT_CAPABILITIES.documentFilters} title={!UNIVERSITY_PASSPORT_CAPABILITIES.documentFilters ? "Backend пока не поддерживает фильтры документов" : undefined} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UniversityDocumentStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(documentStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Документы пока не добавлены" /></section>;
}

function MeetingParticipants({ participants }: { participants: UniversityMeetingRow['participants'] }) {
  return <div className={styles.participants} aria-label={`Участники: ${participants.map((participant) => participant.name).join(', ')}`}>{participants.slice(0, 3).map((participant) => <Avatar initials={participant.initials} size="s" key={participant.id} />)}{participants.length > 3 ? <span className={styles.participantMore}>+{participants.length - 3}</span> : null}</div>;
}

function MeetingsSection({ id, canAdd }: { id: string; canAdd: boolean }) {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState<UniversityMeetingRow | null | undefined>(undefined);
  const [deleteCandidate, setDeleteCandidate] = useState<UniversityMeetingRow | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const canWrite = canAdd && !isMockDataSourceFor('passport');
  const query = useQuery({ queryKey: universityMeetingsQueryKey(id, page), queryFn: ({ signal }) => getUniversityMeetings(id, page, 20, signal), placeholderData: keepPreviousData, staleTime: 30_000 });
  const remove = useMutation({
    mutationFn: (meetingId: string) => deleteUniversityMeeting(meetingId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.meetingsFamily(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.passport(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.historyFamily(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.audit.all }),
      ]);
      setDeleteCandidate(null);
      setMessage('Встреча удалена.');
    },
    onError: (cause) => setMessage(normalizeApiError(cause).message),
  });
  if (query.isPending) return <section className={styles.section} aria-label="Встречи"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  return <section className={`${styles.section} ${styles.meetingSurface}`} aria-label="Встречи">
    {canWrite ? <SectionToolbar title="Встречи"><Button variant="primary" size="s" type="button" onClick={() => setEditor(null)}><Calendar size={16} fill="currentColor" />Добавить встречу</Button></SectionToolbar> : <h2 className={styles.meetingTitle}>Встречи</h2>}
    {query.data.items.length ? <ol className={styles.meetingTimeline}>{query.data.items.slice().sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)).map((meeting) => <li className={styles.meetingItem} key={meeting.id}><div className={styles.meetingMarker} aria-hidden="true" /><article className={styles.meetingContent}><div className={styles.meetingMeta}><time dateTime={meeting.occurredAt}>{formatDateTimeRu(meeting.occurredAt)}</time><span className={styles.meetingType}>{meetingTypeLabels[meeting.type]}</span></div><h3>{meeting.subject}</h3><MeetingParticipants participants={meeting.participants} /><details className={styles.meetingDetails}><summary>Итог и следующее действие</summary><p><strong>Итог:</strong> {meeting.outcome}</p><p><strong>Следующее действие:</strong> {meeting.nextAction}{meeting.dueDate ? ` до ${formatDateRu(meeting.dueDate)}` : ''}</p></details><span className={styles.meetingAuthor}>Автор: {meeting.author}</span>{canWrite ? <div className={styles.assignmentActions}><Button variant="ghost" size="s" type="button" onClick={() => setEditor(meeting)}>Изменить</Button><Button variant="ghost" size="s" type="button" onClick={() => setDeleteCandidate(meeting)}>Удалить</Button></div> : null}</article></li>)}</ol> : <EmptyState icon={<Calendar size={20} fill="currentColor" />} title="Встреч пока нет" description="Записи появятся здесь после первого взаимодействия." headingLevel={3} />}
    {query.data.total > 20 ? <div className={styles.sectionToolbar}><span>Страница {page} из {Math.ceil(query.data.total / 20)}</span><div className={styles.toolbarControls}><Button variant="ghost" size="s" type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>Назад</Button><Button variant="ghost" size="s" type="button" disabled={page * 20 >= query.data.total} onClick={() => setPage(page + 1)}>Далее</Button></div></div> : null}
    {editor !== undefined ? <MeetingMutationForm universityId={id} meeting={editor} onClose={() => setEditor(undefined)} onSaved={() => { setEditor(undefined); setMessage('Встреча сохранена.'); }} /> : null}
    {deleteCandidate ? <Modal title="Удалить встречу?" onClose={() => { if (!remove.isPending) setDeleteCandidate(null); }}><p>Встреча «{deleteCandidate.subject}» будет удалена без возможности восстановления.</p><div className={styles.assignmentActions}><Button variant="ghost" type="button" disabled={remove.isPending} onClick={() => setDeleteCandidate(null)}>Отмена</Button><Button variant="danger" type="button" loading={remove.isPending} disabled={remove.isPending} onClick={() => remove.mutate(deleteCandidate.id)}>Удалить</Button></div></Modal> : null}
    {message ? <div className={styles.toastViewport}><Toast intent={remove.isError ? 'error' : 'success'} title={message} onClose={() => setMessage(null)} /></div> : null}
  </section>;
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview });
      void queryClient.invalidateQueries({ queryKey: queryKeys.audit.all });
      onSuccess();
    },
    onError: (cause) => setError(normalizeApiError(cause, { fallbackMessage: 'Не удалось сменить ответственного.' }).message),
  });

  return <Drawer title="Сменить ответственного" onClose={() => { if (!mutation.isPending) onClose(); }}><div className={styles.assignmentForm}><p className={styles.assignmentIntro}><strong>Текущий ответственный:</strong> {currentName}<br />Выберите пользователя из допустимых кандидатов. Изменение попадёт в паспорт ВУЗа и журнал аудита после ответа сервера.</p>{candidatesQuery.isPending ? <p className={styles.emptySection}>Загрузка кандидатов…</p> : candidatesQuery.isError ? <RouteErrorState compact onRetry={() => void candidatesQuery.refetch()} /> : <label className={styles.filter}><span>Новый ответственный</span><Select value={selectedId} onChange={(event) => setCandidateId(event.target.value)}><option value="" disabled>Выберите пользователя</option>{candidates.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.name} · {candidate.role}</option>)}</Select></label>}<label className={styles.filter}><span>Причина</span><TextArea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Например, перераспределение зоны ответственности" rows={4} /></label>{error ? <p className={styles.assignmentError} role="alert">{error}</p> : null}<div className={styles.assignmentActions}><Button variant="ghost" type="button" disabled={mutation.isPending} onClick={onClose}>Отмена</Button><Button variant="primary" type="button" loading={mutation.isPending} disabled={mutation.isPending || !selectedId || !reason.trim() || candidatesQuery.isError} onClick={() => { setError(null); mutation.mutate(); }}>Сохранить</Button></div></div></Drawer>;
}

function ResponsiblesSection({ id, canEdit }: { id: string; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const [toast, setToast] = useState(false);
  const query = useQuery({ queryKey: universityResponsiblesQueryKey(id), queryFn: () => getUniversityResponsibles(id, queryClient), staleTime: 30_000 });
  if (query.isPending) return <section className={styles.section} aria-label="Ответственные"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  const currentName = query.data.find((person) => person.isPrimary)?.name ?? 'Не назначен';
  return <><section className={styles.section} aria-label="Ответственные">{canEdit ? <SectionToolbar title="Ответственные"><Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Сменить ответственного</Button></SectionToolbar> : null}{query.data.length ? <div className={styles.responsiblesGrid}>{query.data.map((person) => <article className={styles.responsibleCard} key={person.id}><Avatar initials={person.initials} size="m" /><div className={styles.responsibleInfo}><h3>{person.name}</h3><p>{person.role}</p><a href={`mailto:${person.email}`}><Mail size={16} fill="currentColor" />{person.email}</a><a href={`tel:${person.phone.replace(/[^+\d]/g, '')}`}><Phone size={16} fill="currentColor" />{person.phone}</a></div>{person.isPrimary ? <StatusBadge intent="brand">Основной</StatusBadge> : null}</article>)}</div> : <EmptyState icon={<Mail size={20} fill="currentColor" />} title="Ответственные не назначены" description="Контактные лица появятся здесь после назначения." headingLevel={3} />}</section>{assignmentOpen ? <ResponsibleAssignmentDrawer id={id} currentName={currentName} onClose={() => setAssignmentOpen(false)} onSuccess={() => { setAssignmentOpen(false); setToast(true); }} /> : null}{toast ? <Toast intent="success" title="Ответственный изменён" message="Паспорт, история и связанные списки обновляются." onClose={() => setToast(false)} /> : null}</>;
}

export { LicensesSection, DocumentsSection, MeetingsSection, ResponsiblesSection };
