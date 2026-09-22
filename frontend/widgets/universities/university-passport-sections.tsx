'use client';

import Link from 'next/link';
import { useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import Download from '@atomaro/icons/24/action/Download';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import Mail from '@atomaro/icons/24/communication/Mail';
import Phone from '@atomaro/icons/24/technology/Phone';
import { Button } from '@/shared/ui/rtk/button';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { MetricCard } from '@/shared/ui/rtk/metric-card';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { documentStatusIntent, licenseStatusIntent, productStatusIntent, programStatusIntent, readinessIntent } from '@/shared/lib/status-semantics';
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
import styles from './university-passport-sections.module.css';

const formatDate = formatDateRu;

function SectionToolbar({ title, children }: { title?: string; children: ReactNode }) {
  return <div className={styles.sectionToolbar}>{title ? <h2>{title}</h2> : null}<div className={styles.toolbarControls}>{children}</div></div>;
}

const readinessLabels: Record<TeacherReadiness, string> = {
  ready: 'Готов',
  attention: 'Требует внимания',
  expired: 'Просрочено',
};

const productStatusLabels: Record<UniversityProductStatus, string> = {
  active: 'Действует',
  expiring: 'Истекает',
  expired: 'Просрочена',
};

function ProgramStatusBadge({ status }: { status: ProgramStatus }) {
  return <StatusBadge intent={programStatusIntent[status]}>{programStatusLabels[status]}</StatusBadge>;
}

function ReadinessBadge({ readiness }: { readiness: TeacherReadiness }) {
  return <StatusBadge intent={readinessIntent[readiness]}>{readinessLabels[readiness]}</StatusBadge>;
}

function ProductStatusBadge({ status }: { status: UniversityProductStatus }) {
  return <StatusBadge intent={productStatusIntent[status]}>{productStatusLabels[status]}</StatusBadge>;
}

function ProgramFilter({ value, onChange }: { value: ProgramStatus | 'all'; onChange: (value: ProgramStatus | 'all') => void }) {
  return <label className={styles.filter}><span>Статус</span><select value={value} onChange={(event) => onChange(event.target.value as ProgramStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(programStatusLabels).map(([status, label]) => <option value={status} key={status}>{label}</option>)}</select></label>;
}

function TeacherFilter({ value, onChange }: { value: TeacherReadiness | 'all'; onChange: (value: TeacherReadiness | 'all') => void }) {
  return <label className={styles.filter}><span>Готовность</span><select value={value} onChange={(event) => onChange(event.target.value as TeacherReadiness | 'all')}><option value="all">Все статусы</option>{Object.entries(readinessLabels).map(([status, label]) => <option value={status} key={status}>{label}</option>)}</select></label>;
}

function ProgramRow({ row }: { row: UniversityProgramRow }) {
  return <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.id.split('-').at(-1) ? `Программа ${row.id.split('-').at(-1)}` : 'Программа'}</span></>;
}

function ProgramsSection({ id }: { id: string }) {
  const [statusFilter, setStatusFilter] = useState<ProgramStatus | 'all'>('all');
  const query = useQuery({ queryKey: universityProgramsQueryKey(id), queryFn: () => getUniversityPrograms(id), staleTime: 30_000 });
  const rows = useMemo(() => query.data?.filter((row) => statusFilter === 'all' || row.status === statusFilter) ?? [], [query.data, statusFilter]);
  const columns: PassportTableColumn<UniversityProgramRow>[] = [
    { id: 'direction', label: 'Направление', sortable: true, sortValue: (row) => row.direction, render: (row) => row.direction },
    { id: 'name', label: 'Программа', sortable: true, sortValue: (row) => row.name, render: (row) => <ProgramRow row={row} /> },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => programStatusLabels[row.status], render: (row) => <ProgramStatusBadge status={row.status} /> },
    { id: 'launchDate', label: 'Дата запуска', sortable: true, sortValue: (row) => row.launchDate, render: (row) => formatDate(row.launchDate) },
    { id: 'responsible', label: 'Ответственный', sortable: true, sortValue: (row) => row.responsible?.name ?? '', render: (row) => row.responsible?.name ?? 'Не назначен' },
    { id: 'teachers', label: 'Преподаватели', sortable: true, sortValue: (row) => row.teachersCount, render: (row) => row.teachersCount },
    { id: 'students', label: 'Студенты', sortable: true, sortValue: (row) => row.studentsCount, render: (row) => row.studentsCount },
    { id: 'actions', label: 'Действия', render: () => <Button variant="ghost" size="s" type="button" disabled title="Детали программы появятся после подключения маршрута">Открыть</Button> },
  ];
  const mobileFields: PassportMobileField<UniversityProgramRow>[] = [
    { label: 'Программа', render: (row) => <ProgramRow row={row} /> },
    { label: 'Направление', render: (row) => row.direction },
    { label: 'Статус', render: (row) => <ProgramStatusBadge status={row.status} /> },
    { label: 'Запуск', render: (row) => formatDate(row.launchDate) },
    { label: 'Ответственный', render: (row) => row.responsible?.name ?? 'Не назначен' },
    { label: 'Состав', render: (row) => `${row.teachersCount} преподавателей · ${row.studentsCount} студентов` },
    { label: 'Действия', render: () => <Button variant="ghost" size="s" type="button" disabled title="Детали программы появятся после подключения маршрута">Открыть</Button> },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Программы"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-label="Программы"><SectionToolbar><ProgramFilter value={statusFilter} onChange={setStatusFilter} /></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет программ с выбранным статусом" /></section>;
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
    { id: 'readiness', label: 'Готовность', sortable: true, sortValue: (row) => ({ expired: 0, attention: 1, ready: 2 }[row.readiness]), render: (row) => <ReadinessBadge readiness={row.readiness} /> },
    { id: 'training', label: 'Следующее обучение', sortable: true, sortValue: (row) => row.nextTrainingDate, render: (row) => formatDate(row.nextTrainingDate) },
    { id: 'programs', label: 'Программы', render: (row) => <ProgramChips programs={row.allowedPrograms} /> },
    { id: 'actions', label: 'Действия', render: (row) => <Link className={styles.actionLink} href={`/teachers/${row.id}`}>Открыть</Link> },
  ];
  const mobileFields: PassportMobileField<UniversityTeacherRow>[] = [
    { label: 'ФИО', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { label: 'Должность', render: (row) => row.position },
    { label: 'Готовность', render: (row) => <ReadinessBadge readiness={row.readiness} /> },
    { label: 'Обучение', render: (row) => formatDate(row.nextTrainingDate) },
    { label: 'Программы', render: (row) => <ProgramChips programs={row.allowedPrograms} /> },
    { label: 'Действия', render: (row) => <Link className={styles.actionLink} href={`/teachers/${row.id}`}>Открыть профиль</Link> },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Преподаватели"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-label="Преподаватели"><SectionToolbar title="Преподаватели"><TeacherFilter value={readinessFilter} onChange={setReadinessFilter} /></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет преподавателей с выбранным статусом" /></section>;
}

function StudentSummary({ total, active, graduated, academicLeave }: { total: number; active: number; graduated: number; academicLeave: number }) {
  const metrics = [['Всего', total], ['Активные', active], ['Выпущены', graduated], ['Академический отпуск', academicLeave]] as const;
  return <div className={styles.studentSummary} aria-label="Сводка по студентам">{metrics.map(([label, value]) => <MetricCard label={label} value={value} centered key={label} />)}</div>;
}

function StudentsSection({ id }: { id: string }) {
  const query = useQuery({ queryKey: universityStudentsQueryKey(id), queryFn: () => getUniversityStudentsSummary(id), staleTime: 30_000 });
  const columns: PassportTableColumn<UniversityStudentsByProgram>[] = [
    { id: 'programName', label: 'Программа', sortable: true, sortValue: (row) => row.programName, render: (row) => <strong className={styles.primaryCell}>{row.programName}</strong> },
    { id: 'active', label: 'Активные', sortable: true, sortValue: (row) => row.active, render: (row) => row.active },
    { id: 'graduated', label: 'Выпущены', sortable: true, sortValue: (row) => row.graduated, render: (row) => row.graduated },
    { id: 'total', label: 'Всего', sortable: true, sortValue: (row) => row.total, render: (row) => row.total },
  ];
  const mobileFields: PassportMobileField<UniversityStudentsByProgram>[] = [
    { label: 'Программа', render: (row) => <strong className={styles.primaryCell}>{row.programName}</strong> },
    { label: 'Активные', render: (row) => row.active },
    { label: 'Выпущены', render: (row) => row.graduated },
    { label: 'Всего', render: (row) => row.total },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="Студенты"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <div className={styles.studentPage}><StudentSummary total={query.data.total} active={query.data.active} graduated={query.data.graduated} academicLeave={query.data.academicLeave} /><section className={styles.section} aria-label="Студенты по программам"><PassportDataTable rows={query.data.byProgram.map((row) => ({ ...row, id: row.programId }))} columns={columns} mobileFields={mobileFields} emptyMessage="Нет данных по студентам" /></section></div>;
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
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

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
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Лицензии"><SectionToolbar><label className={styles.filter}><span>Статус</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UniversityLicenseStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(licenseStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Лицензии пока не добавлены" /></section>;
}

function DocumentFile({ row }: { row: UniversityDocumentRow }) {
  return <div className={styles.fileCell}><DocumentText size={20} fill="currentColor" /><div><strong className={styles.primaryCell}>{row.fileName}</strong><span className={styles.secondaryCell}>{row.fileSize}</span></div></div>;
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
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Документы"><SectionToolbar><div className={styles.filtersRow}><label className={styles.filter}><span>Тип</span><select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="all">Все типы</option>{types.map((type) => <option value={type} key={type}>{type}</option>)}</select></label><label className={styles.filter}><span>Статус</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UniversityDocumentStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(documentStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div></SectionToolbar><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Документы пока не добавлены" /></section>;
}

function MeetingParticipants({ participants }: { participants: UniversityMeetingRow['participants'] }) {
  return <div className={styles.participants} aria-label={`Участники: ${participants.map((participant) => participant.name).join(', ')}`}>{participants.slice(0, 3).map((participant) => <Avatar initials={participant.initials} size="s" key={participant.id} />)}{participants.length > 3 ? <span className={styles.participantMore}>+{participants.length - 3}</span> : null}</div>;
}

function MeetingsSection({ id, canAdd }: { id: string; canAdd: boolean }) {
  const query = useQuery({ queryKey: universityMeetingsQueryKey(id), queryFn: () => getUniversityMeetings(id), staleTime: 30_000 });
  if (query.isPending) return <section className={styles.section} aria-label="Встречи"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Встречи">{canAdd ? <SectionToolbar><Button variant="primary" size="s" type="button" disabled title="Создание встречи подключится после появления API"><Calendar size={16} fill="currentColor" />Добавить встречу</Button></SectionToolbar> : null}{query.data.length ? <ol className={styles.meetingTimeline}>{query.data.slice().sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)).map((meeting) => <li className={styles.meetingItem} key={meeting.id}><div className={styles.meetingMarker} aria-hidden="true" /><article className={styles.meetingContent}><div className={styles.meetingMeta}><time dateTime={meeting.occurredAt}>{formatDateTimeRu(meeting.occurredAt)}</time><span className={styles.meetingType}>{meetingTypeLabels[meeting.type]}</span></div><h3>{meeting.subject}</h3><MeetingParticipants participants={meeting.participants} /><details className={styles.meetingDetails}><summary>Итог и следующее действие</summary><p><strong>Итог:</strong> {meeting.outcome}</p><p><strong>Следующее действие:</strong> {meeting.nextAction}{meeting.dueDate ? ` до ${formatDateRu(meeting.dueDate)}` : ''}</p></details><span className={styles.meetingAuthor}>Автор: {meeting.author}</span></article></li>)}</ol> : <p className={styles.emptySection} role="status">Нет данных для отображения</p>}</section>;
}

function ResponsiblesSection({ id }: { id: string }) {
  const query = useQuery({ queryKey: universityResponsiblesQueryKey(id), queryFn: () => getUniversityResponsibles(id), staleTime: 30_000 });
  if (query.isPending) return <section className={styles.section} aria-label="Ответственные"><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  return <section className={styles.section} aria-label="Ответственные">{query.data.length ? <div className={styles.responsiblesGrid}>{query.data.map((person) => <article className={styles.responsibleCard} key={person.id}><Avatar initials={person.initials} size="m" /><div className={styles.responsibleInfo}><h3>{person.name}</h3><p>{person.role}</p><a href={`mailto:${person.email}`}><Mail size={16} fill="currentColor" />{person.email}</a><a href={`tel:${person.phone.replace(/[^+\d]/g, '')}`}><Phone size={16} fill="currentColor" />{person.phone}</a></div>{person.isPrimary ? <StatusBadge intent="brand">Основной</StatusBadge> : null}</article>)}</div> : <p className={styles.emptySection} role="status">Нет данных для отображения</p>}</section>;
}

export { LicensesSection, DocumentsSection, MeetingsSection, ResponsiblesSection };
