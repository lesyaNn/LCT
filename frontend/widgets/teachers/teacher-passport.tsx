'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import Download from '@atomaro/icons/24/action/Download';
import Education from '@atomaro/icons/24/culture/Education';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import Edit from '@atomaro/icons/24/editor/Edit';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatDateRu, formatDaysUntilRu, getExpirationStatus } from '@/shared/lib/formatters';
import { expirationStatusIntent, expirationStatusLabels, readinessIntent, readinessLabels } from '@/shared/lib/status-semantics';
import {
  getTeacherPassport,
  teacherPassportQueryKey,
  type TeacherCertificate,
  type TeacherQualification,
  type TeacherPassportProfile,
  type TeacherReadiness,
  type TeacherTraining,
} from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from '@/widgets/universities/passport-data-table';
import styles from './teacher-passport.module.css';

function SectionHeading({ id, title, description }: { id: string; title: string; description?: string }) {
  return <div className={styles.sectionHeading}><div><h2 id={id}>{title}</h2>{description ? <p>{description}</p> : null}</div></div>;
}

function ReadinessBadge({ readiness }: { readiness: TeacherReadiness }) {
  return <StatusBadge intent={readinessIntent[readiness]}>{readinessLabels[readiness]}</StatusBadge>;
}

function ExpirationBadge({ status }: { status: TeacherQualification['status'] }) {
  return <StatusBadge intent={expirationStatusIntent[status]}>{expirationStatusLabels[status]}</StatusBadge>;
}

function DocumentCell({ document }: { document: TeacherQualification['document'] | TeacherCertificate['document'] }) {
  if (!document) return <span className={styles.muted}>Не приложен</span>;
  return (
    <div className={styles.documentCell}>
      <DocumentText size={20} fill="currentColor" aria-hidden="true" />
      <div className={styles.documentInfo}>
        <strong>{document.name}</strong>
        <span>{document.fileType} · {document.fileSize}</span>
      </div>
      {document.downloadUrl ? <a className={styles.iconAction} href={document.downloadUrl} download aria-label={`Скачать ${document.name}`}><Download size={17} fill="currentColor" /></a> : null}
    </div>
  );
}

function CertificateStatus({ row }: { row: TeacherCertificate }) {
  return (
    <div className={row.mandatory && row.status === 'expired' ? styles.criticalStatus : styles.statusCell}>
      <span className={styles.statusWithIcon}>{row.mandatory && row.status === 'expired' ? <ErrorStroke size={16} fill="currentColor" aria-hidden="true" /> : null}<StatusBadge intent={expirationStatusIntent[row.status]}>{expirationStatusLabels[row.status]}</StatusBadge></span>
      {row.status !== 'current' ? <span className={styles.statusContext}>{formatDaysUntilRu(row.expiresAt)}</span> : null}
    </div>
  );
}

function MandatoryBadge({ mandatory }: { mandatory: boolean }) {
  return <StatusBadge intent={mandatory ? 'brand' : 'neutral'}>{mandatory ? 'Да' : 'Нет'}</StatusBadge>;
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

function CertificatesSection({ rows }: { rows: TeacherCertificate[] }) {
  const columns: PassportTableColumn<TeacherCertificate>[] = [
    { id: 'name', label: 'Сертификат', sortable: true, sortValue: (row) => row.name, render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'issuer', label: 'Кем выдан', sortable: true, sortValue: (row) => row.issuer, render: (row) => row.issuer },
    { id: 'issuedAt', label: 'Выдан', sortable: true, sortValue: (row) => row.issuedAt, render: (row) => formatDateRu(row.issuedAt) },
    { id: 'expiresAt', label: 'Истекает', sortable: true, sortValue: (row) => row.expiresAt, render: (row) => formatDateRu(row.expiresAt) },
    { id: 'mandatory', label: 'Обязательный', sortable: true, sortValue: (row) => Number(row.mandatory), render: (row) => <MandatoryBadge mandatory={row.mandatory} /> },
    { id: 'program', label: 'Программа', sortable: true, sortValue: (row) => row.program, render: (row) => row.program },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => row.status, render: (row) => <CertificateStatus row={row} /> },
  ];
  const mobileFields: PassportMobileField<TeacherCertificate>[] = [
    { label: 'Сертификат', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { label: 'Статус', render: (row) => <CertificateStatus row={row} /> },
    { label: 'Обязательный', render: (row) => <MandatoryBadge mandatory={row.mandatory} /> },
    { label: 'Кем выдан', render: (row) => row.issuer },
    { label: 'Истекает', render: (row) => formatDateRu(row.expiresAt) },
    { label: 'Программа', render: (row) => row.program },
  ];
  return <section className={styles.section} aria-labelledby="teacher-certificates-title"><SectionHeading id="teacher-certificates-title" title="Сертификаты" description="Обязательные сертификаты влияют на готовность преподавателя и Health Score вуза." /><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Сертификаты пока не добавлены" /></section>;
}

function AllowedProgramsSection({ programs }: { programs: Array<{ id: string; name: string }> }) {
  return (
    <section className={styles.section} aria-labelledby="teacher-programs-title">
      <SectionHeading id="teacher-programs-title" title="Разрешённые программы" description="Программы, в которых преподаватель может участвовать." />
      <div className={styles.programsSurface}>
        {programs.length ? <div className={styles.chips} aria-label={`Разрешённые программы: ${programs.map((program) => program.name).join(', ')}`}>{programs.map((program) => <span className={styles.chip} key={program.id}>{program.name}</span>)}</div> : <p className={styles.emptyMessage}>Нет разрешённых программ</p>}
      </div>
    </section>
  );
}

function TeacherHeader({ id, teacher }: { id: string; teacher: TeacherPassportProfile }) {
  const { user } = useAuth();
  const canEdit = user?.role === 'admin';
  const canReport = user?.role === 'admin' || user?.role === 'manager';
  const nextTrainingStatus = getExpirationStatus(teacher.nextTrainingDate);
  return (
    <header className={styles.header}>
      <div className={styles.breadcrumbs}><Link href="/teachers">Преподаватели</Link><span aria-hidden="true">/</span><span>Паспорт преподавателя</span></div>
      <div className={styles.headerGrid}>
        <div className={styles.identity}>
          <p className={styles.eyebrow}>ПАСПОРТ ПРЕПОДАВАТЕЛЯ</p>
          <h1>{teacher.name}</h1>
          <div className={styles.metaList}>
            <span><span className={styles.metaLabel}>ВУЗ</span><Link className={styles.universityLink} href={`/universities/${teacher.universityId}`}>{teacher.universityName}</Link></span>
            <span><span className={styles.metaLabel}>Должность</span>{teacher.position}</span>
          </div>
        </div>
        <div className={styles.statusPanel} aria-label="Готовность преподавателя">
          <div className={styles.statusPanelTop}><span className={styles.overline}>Readiness</span><ReadinessBadge readiness={teacher.readiness} /></div>
          <p className={styles.readinessReason}>{teacher.readinessReason}</p>
          <div className={styles.nextTraining}><TimeStroke size={18} fill="currentColor" aria-hidden="true" /><div><span>Следующее повышение квалификации</span><strong>{formatDateRu(teacher.nextTrainingDate)}</strong>{nextTrainingStatus !== 'current' ? <small className={nextTrainingStatus === 'expired' ? styles.expiredText : styles.warningText}>{formatDaysUntilRu(teacher.nextTrainingDate)}</small> : null}</div></div>
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
  return <div className={styles.skeletonPage} aria-live="polite" aria-busy="true"><span className={styles.skeletonLine} /><span className={`${styles.skeletonLine} ${styles.skeletonTitle}`} /><div className={styles.skeletonHeader} /><span className={`${styles.skeletonLine} ${styles.skeletonSection}`} /><PassportTableSkeleton /><span className={`${styles.skeletonLine} ${styles.skeletonSection}`} /><PassportTableSkeleton /></div>;
}

export function TeacherPassport({ id }: { id: string }) {
  const query = useQuery({ queryKey: teacherPassportQueryKey(id), queryFn: () => getTeacherPassport(id), staleTime: 30_000 });
  if (query.isPending) return <TeacherPassportSkeleton />;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  return <div className={styles.page}><TeacherHeader id={id} teacher={query.data.teacher} /><div className={styles.sections}><QualificationsSection rows={query.data.qualifications} /><TrainingsSection rows={query.data.trainings} /><CertificatesSection rows={query.data.certificates} /><AllowedProgramsSection programs={query.data.allowedPrograms} /></div><Link className={styles.backLink} href="/teachers"><ArrowRight size={16} fill="currentColor" />Вернуться к списку преподавателей</Link></div>;
}
