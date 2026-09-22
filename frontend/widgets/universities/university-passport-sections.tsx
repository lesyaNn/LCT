'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/shared/ui/rtk/button';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import {
  getUniversityProducts,
  getUniversityPrograms,
  getUniversityStudentsSummary,
  getUniversityTeachers,
  programStatusLabels,
  universityProductsQueryKey,
  universityProgramsQueryKey,
  universityStudentsQueryKey,
  universityTeachersQueryKey,
  type ProgramStatus,
  type TeacherReadiness,
  type UniversityProductRow,
  type UniversityProductStatus,
  type UniversityProgramRow,
  type UniversityStudentsByProgram,
  type UniversityTeacherRow,
} from '@/shared/lib/universities-repository';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from './passport-data-table';
import styles from './university-passport-sections.module.css';

const formatDate = (isoDate: string) => new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(new Date(isoDate));

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

function SectionHeader({ title, description, id }: { title: string; description: string; id: string }) {
  return <div className={styles.sectionHeader}><div><h2 id={id}>{title}</h2><p>{description}</p></div></div>;
}

function StatusBadge({ tone, children }: { tone: 'neutral' | 'brand' | 'success' | 'warning' | 'danger'; children: string }) {
  return <span className={`${styles.statusBadge} ${styles[`status-${tone}`]}`}><span className={styles.statusDot} aria-hidden="true" />{children}</span>;
}

function ProgramStatusBadge({ status }: { status: ProgramStatus }) {
  const tone = status === 'launched' ? 'success' : status === 'active' ? 'brand' : status === 'planned' ? 'neutral' : 'warning';
  return <StatusBadge tone={tone}>{programStatusLabels[status]}</StatusBadge>;
}

function ReadinessBadge({ readiness }: { readiness: TeacherReadiness }) {
  const tone = readiness === 'ready' ? 'success' : readiness === 'attention' ? 'warning' : 'danger';
  return <StatusBadge tone={tone}>{readinessLabels[readiness]}</StatusBadge>;
}

function ProductStatusBadge({ status }: { status: UniversityProductStatus }) {
  const tone = status === 'active' ? 'success' : status === 'expiring' ? 'warning' : 'danger';
  return <StatusBadge tone={tone}>{productStatusLabels[status]}</StatusBadge>;
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

  if (query.isPending) return <section className={styles.section}><SectionHeader id="programs-section-title" title="Программы" description="Образовательные программы и их запуск" /><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-labelledby="programs-section-title"><div className={styles.sectionToolbar}><SectionHeader id="programs-section-title" title="Программы" description="Образовательные программы и их запуск" /><ProgramFilter value={statusFilter} onChange={setStatusFilter} /></div><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет программ с выбранным статусом" /></section>;
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

  if (query.isPending) return <section className={styles.section}><SectionHeader id="teachers-section-title" title="Преподаватели" description="Состав команды и готовность к занятиям" /><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-labelledby="teachers-section-title"><div className={styles.sectionToolbar}><SectionHeader id="teachers-section-title" title="Преподаватели" description="Состав команды и готовность к занятиям" /><TeacherFilter value={readinessFilter} onChange={setReadinessFilter} /></div><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Нет преподавателей с выбранным статусом" /></section>;
}

function StudentSummary({ total, active, graduated, academicLeave }: { total: number; active: number; graduated: number; academicLeave: number }) {
  const metrics = [['Всего', total], ['Активные', active], ['Выпущены', graduated], ['Академический отпуск', academicLeave]] as const;
  return <div className={styles.studentSummary} aria-label="Сводка по студентам">{metrics.map(([label, value]) => <div className={styles.studentMetric} key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>;
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

  if (query.isPending) return <section className={styles.section}><SectionHeader id="students-section-title" title="Студенты" description="Агрегированная статистика без персональных данных" /><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-labelledby="students-section-title"><SectionHeader id="students-section-title" title="Студенты" description="Агрегированная статистика без персональных данных" /><StudentSummary total={query.data.total} active={query.data.active} graduated={query.data.graduated} academicLeave={query.data.academicLeave} /><PassportDataTable rows={query.data.byProgram.map((row) => ({ ...row, id: row.programId }))} columns={columns} mobileFields={mobileFields} emptyMessage="Нет данных по студентам" /></section>;
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

  if (query.isPending) return <section className={styles.section}><SectionHeader id="products-section-title" title="Продукты" description="Подключённые продукты и лицензии" /><PassportTableSkeleton /></section>;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-labelledby="products-section-title"><SectionHeader id="products-section-title" title="Продукты" description="Подключённые продукты и лицензии" /><PassportDataTable rows={query.data} columns={columns} mobileFields={mobileFields} emptyMessage="Нет подключённых продуктов" /></section>;
}

export { ProgramsSection, ProductsSection, StudentsSection, TeachersSection };
