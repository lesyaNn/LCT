'use client';

import { PassportDataTable, type PassportMobileField, type PassportTableColumn } from '@/widgets/universities/passport-data-table';
import { formatDateRu } from '@/shared/lib/formatters';
import { programStatusIntent } from '@/shared/lib/status-semantics';
import { programStatusLabels, type TeacherProgramAssignment } from '@/shared/lib/universities-repository';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './teacher-passport.module.css';

function ProgramStatus({ status }: { status: TeacherProgramAssignment['status'] }) {
  return <StatusBadge intent={programStatusIntent[status]}>{programStatusLabels[status]}</StatusBadge>;
}

function CanTeach({ value }: { value: boolean }) {
  return <StatusBadge intent={value ? 'success' : 'neutral'}>{value ? 'Да' : 'Нет'}</StatusBadge>;
}

export function TeacherProgramsSection({ rows }: { rows: TeacherProgramAssignment[] }) {
  const columns: PassportTableColumn<TeacherProgramAssignment>[] = [
    { id: 'name', label: 'Программа', sortable: true, sortValue: (row) => row.name, render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { id: 'direction', label: 'Направление', sortable: true, sortValue: (row) => row.direction, render: (row) => row.direction },
    { id: 'canTeach', label: 'Может вести', sortable: true, sortValue: (row) => Number(row.canTeach), render: (row) => <CanTeach value={row.canTeach} /> },
    { id: 'assignedAt', label: 'Назначен', sortable: true, sortValue: (row) => row.assignedAt, render: (row) => formatDateRu(row.assignedAt) },
    { id: 'status', label: 'Статус программы', sortable: true, sortValue: (row) => programStatusLabels[row.status], render: (row) => <ProgramStatus status={row.status} /> },
  ];
  const mobileFields: PassportMobileField<TeacherProgramAssignment>[] = [
    { label: 'Программа', render: (row) => <strong className={styles.primaryCell}>{row.name}</strong> },
    { label: 'Направление', render: (row) => row.direction },
    { label: 'Может вести', render: (row) => <CanTeach value={row.canTeach} /> },
    { label: 'Назначен', render: (row) => formatDateRu(row.assignedAt) },
    { label: 'Статус программы', render: (row) => <ProgramStatus status={row.status} /> },
  ];
  return <section className={styles.section} aria-labelledby="teacher-programs-title"><div className={styles.sectionHeading}><div><h2 id="teacher-programs-title">Разрешённые программы</h2><p>Назначения и доступность преподавателя для образовательных программ.</p></div></div><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Разрешённые программы не назначены" /></section>;
}
