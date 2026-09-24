'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import Download from '@atomaro/icons/24/action/Download';
import Education from '@atomaro/icons/24/culture/Education';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import Edit from '@atomaro/icons/24/editor/Edit';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatDateRu, formatDaysUntilRu, getUpcomingDateStatus } from '@/shared/lib/formatters';
import { expirationStatusIntent, expirationStatusLabels, upcomingDateIntent } from '@/shared/lib/status-semantics';
import {
  getTeacherPassport,
  teacherPassportQueryKey,
  type TeacherQualification,
  type TeacherPassportProfile,
  type TeacherTraining,
} from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { ReadinessBadge } from '@/shared/ui/rtk/readiness-badge';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Skeleton, SkeletonGroup, TableSkeleton } from '@/shared/ui/skeleton';
import { PassportDataTable, type PassportMobileField, type PassportTableColumn } from '@/widgets/universities/passport-data-table';
import { TeacherCertificatesSection } from './teacher-certificates-section';
import { TeacherProgramsSection } from './teacher-programs-section';
import styles from './teacher-passport.module.css';

function SectionHeading({ id, title, description }: { id: string; title: string; description?: string }) {
  return <div className={styles.sectionHeading}><div><h2 id={id}>{title}</h2>{description ? <p>{description}</p> : null}</div></div>;
}

function ExpirationBadge({ status }: { status: TeacherQualification['status'] }) {
  return <StatusBadge intent={expirationStatusIntent[status]}>{expirationStatusLabels[status]}</StatusBadge>;
}

function DocumentCell({ document }: { document: TeacherQualification['document'] }) {
  if (!document) return <span className={styles.muted}>Не приложен</span>;
  return (
    <div className={styles.documentCell}>
      <DocumentText size={20} fill="currentColor" aria-hidden="true" />
      <div className={styles.documentInfo}>
        <strong title={document.name}>{document.name}</strong>
        <span>{document.fileType} · {document.fileSize}</span>
      </div>
      {document.downloadUrl ? <a className={styles.iconAction} href={document.downloadUrl} download aria-label={`Скачать ${document.name}`}><Download size={17} fill="currentColor" /></a> : null}
    </div>
  );
}

function QualificationsSection({ rows }: { rows: TeacherQualification[] }) {
  const columns: PassportTableColumn<TeacherQualification>[] = [
    { id: 'name', label: 'Квалификация', sortable: true, sortValue: (row) => row.name, render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'obtainedAt', label: 'Получена', sortable: true, sortValue: (row) => row.obtainedAt, render: (row) => formatDateRu(row.obtainedAt) },
    { id: 'expiresAt', label: 'Истекает', sortable: true, sortValue: (row) => row.expiresAt, render: (row) => formatDateRu(row.expiresAt) },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => row.status, render: (row) => <ExpirationBadge status={row.status} /> },
    { id: 'document', label: 'Документ', render: (row) => <DocumentCell document={row.document} /> },
  ];
  const mobileFields: PassportMobileField<TeacherQualification>[] = [
    { label: 'Квалификация', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { label: 'Статус', render: (row) => <ExpirationBadge status={row.status} /> },
    { label: 'Получена', render: (row) => formatDateRu(row.obtainedAt) },
    { label: 'Истекает', render: (row) => formatDateRu(row.expiresAt) },
    { label: 'Документ', render: (row) => <DocumentCell document={row.document} /> },
  ];
  return <section className={styles.section} aria-labelledby="teacher-qualifications-title"><SectionHeading id="teacher-qualifications-title" title="Квалификации" description="Подтверждённые квалификации и сроки действия документов." /><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Квалификации не добавлены" /></section>;
}

function TrainingsSection({ rows }: { rows: TeacherTraining[] }) {
  const columns: PassportTableColumn<TeacherTraining>[] = [
    { id: 'name', label: 'Обучение', sortable: true, sortValue: (row) => row.name, render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'provider', label: 'Организатор', sortable: true, sortValue: (row) => row.provider, render: (row) => row.provider },
    { id: 'completedAt', label: 'Завершено', sortable: true, sortValue: (row) => row.completedAt, render: (row) => formatDateRu(row.completedAt) },
    { id: 'hours', label: 'Часы', sortable: true, sortValue: (row) => row.hours, render: (row) => `${row.hours} ч` },
    { id: 'certificate', label: 'Сертификат', render: (row) => row.certificate ?? <span className={styles.muted}>Не выдан</span> },
  ];
  const mobileFields: PassportMobileField<TeacherTraining>[] = [
    { label: 'Обучение', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { label: 'Организатор', render: (row) => row.provider },
    { label: 'Завершено', render: (row) => formatDateRu(row.completedAt) },
    { label: 'Часы', render: (row) => `${row.hours} ч` },
    { label: 'Сертификат', render: (row) => row.certificate ?? <span className={styles.muted}>Не выдан</span> },
  ];
  return <section className={styles.section} aria-labelledby="teacher-trainings-title"><SectionHeading id="teacher-trainings-title" title="Обучения" description="Завершённые курсы и тренинги преподавателя." /><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Обучения пока отсутствуют" /></section>;
}

function TeacherHeader({ id, teacher }: { id: string; teacher: TeacherPassportProfile }) {
  const { user } = useAuth();
  const canEdit = user?.role === 'admin';
  const canReport = user?.role === 'admin' || user?.role === 'manager';
  const nextTrainingStatus = getUpcomingDateStatus(teacher.nextTrainingDate);
  return (
    <header className={styles.header}>
      <div className={styles.headerGrid}>
        <div className={styles.identity}>
          <h1>{teacher.name}</h1>
          <div className={styles.metaList}>
            <Link className={styles.universityLink} href={`/universities/${teacher.universityId}`}>{teacher.universityName}</Link>
            <span className={styles.position}>{teacher.position}</span>
          </div>
        </div>
        <div className={styles.statusPanel} aria-label="Готовность преподавателя">
          <div className={styles.statusPanelTop}><span className={styles.overline}>Готовность</span></div>
          <ReadinessBadge readiness={teacher.readiness} reason={teacher.readinessReason} size="lg" showDetails />
          <div className={styles.nextTraining}><TimeStroke size={18} fill="currentColor" aria-hidden="true" /><div><span>Следующее повышение квалификации</span>{!teacher.qualificationRequired ? <strong>Повышение не требуется</strong> : teacher.nextTrainingDate ? <><strong>{formatDateRu(teacher.nextTrainingDate)}</strong><StatusBadge intent={upcomingDateIntent[nextTrainingStatus]} variant="inline">{formatDaysUntilRu(teacher.nextTrainingDate)}</StatusBadge></> : <strong>Данные отсутствуют</strong>}</div></div>
          <div className={styles.headerActions} aria-label="Действия с преподавателем">
            {canEdit ? <Button variant="secondary" size="s" type="button" disabled title="Редактирование подключится после появления API"><Edit size={16} fill="currentColor" />Редактировать</Button> : null}
            {canReport ? <Button variant="primary" size="s" type="button" disabled title="Формирование отчёта подключится после появления API"><Education size={16} fill="currentColor" />Отчёт</Button> : null}
          </div>
        </div>
      </div>
      <p className={styles.routeHint}>Идентификатор преподавателя: <code>{id}</code></p>
    </header>
  );
}

function TeacherPassportSkeleton() {
  return <SkeletonGroup label="Загрузка паспорта преподавателя"><Skeleton variant="text" width="220px" /><Skeleton variant="text" width="min(72%, 520px)" height={36} /><Skeleton height={210} /><TableSkeleton rows={4} columns={5} label="Загрузка квалификаций" /><TableSkeleton rows={4} columns={5} label="Загрузка обучений" /></SkeletonGroup>;
}

export function TeacherPassport({ id }: { id: string }) {
  const query = useQuery({ queryKey: teacherPassportQueryKey(id), queryFn: () => getTeacherPassport(id), staleTime: 30_000 });
  if (query.isPending) return <TeacherPassportSkeleton />;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  return <div className={styles.page}><TeacherHeader id={id} teacher={query.data.teacher} /><div className={styles.sections}><QualificationsSection rows={query.data.qualifications} /><TrainingsSection rows={query.data.trainings} /><TeacherCertificatesSection rows={query.data.certificates} /><TeacherProgramsSection rows={query.data.allowedPrograms} /></div><Link className={styles.backLink} href="/teachers"><ArrowRight size={16} fill="currentColor" />Вернуться к списку преподавателей</Link></div>;
}
