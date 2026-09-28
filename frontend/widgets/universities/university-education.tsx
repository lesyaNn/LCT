'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import {
  addTeacherProgram, createTeacher, educationKeys, educationStatistics,
  integrationCapabilities, listTeachers, syncDemoLms, updateTeacher,
  updateTeacherProgram, type TeacherProgram, type TeacherRecord,
  type TrainingStatus, type UniversityEducationStats,
} from '@/shared/lib/education-repository';
import { formatDateRu } from '@/shared/lib/formatters';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from './passport-data-table';
import { Button } from '@/shared/ui/rtk/button';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './university-education.module.css';

const statusLabels: Record<TrainingStatus, string> = {
  not_started: 'Не начато', in_progress: 'В процессе',
  completed: 'Выполнено', needs_review: 'Нужна проверка',
};

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className={styles.metric}><strong>{value}</strong><span>{label}</span></div>;
}

export function EducationOverview({ id }: { id: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const stats = useQuery({ queryKey: educationKeys.stats(id), queryFn: () => educationStatistics(id), staleTime: 30_000 });
  const capabilities = useQuery({ queryKey: ['integrations', 'capabilities'], queryFn: integrationCapabilities, staleTime: 60_000 });
  const [error, setError] = useState('');
  const sync = useMutation({
    mutationFn: () => syncDemoLms(id),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: educationKeys.family(id) }); setError(''); },
    onError: (cause) => setError(normalizeApiError(cause).message),
  });
  return <section className={styles.section} aria-label="Статистика обучения">
    <div className={styles.header}><div><h2>Статистика обучения</h2><p>Показатели по программам из LMS и сайта</p></div>
      {hasPermission(user, 'university.edit') && capabilities.data?.demo_lms_enabled
        ? <Button variant="ghost" size="s" type="button" loading={sync.isPending} onClick={() => sync.mutate()}>Обновить из TEST/DEMO LMS</Button> : null}
    </div>
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
    {stats.isPending ? <PassportTableSkeleton /> : stats.isError || !stats.data
      ? <RouteErrorState compact onRetry={() => void stats.refetch()} />
      : <><div className={styles.metrics}>
        <Metric label="Обучающихся" value={stats.data.programs.some((program) => program.learner_source) ? stats.data.learners_count : '—'} />
        <Metric label="Заявок" value={stats.data.programs.some((program) => program.applications_synced_at) ? stats.data.applications_count : '—'} />
        <Metric label="Потоков" value={stats.data.programs.some((program) => program.learner_source) ? stats.data.flows_count : '—'} />
      </div><p className={styles.meta}>Источник и дата обновления указаны для каждой программы ниже. Персональные данные обучающихся в CRM не хранятся.</p></>}
  </section>;
}

type TeacherAction = { kind: 'create' } | { kind: 'name'; teacher: TeacherRecord } |
  { kind: 'add-program'; teacher: TeacherRecord } |
  { kind: 'program'; teacher: TeacherRecord; program: TeacherProgram };

function TeacherForm({ universityId, action, stats, onClose }: {
  universityId: string; action: TeacherAction; stats: UniversityEducationStats; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const teacher = 'teacher' in action ? action.teacher : null;
  const currentProgram = action.kind === 'program' ? action.program : null;
  const [name, setName] = useState(teacher?.full_name ?? '');
  const [programId, setProgramId] = useState(currentProgram?.program_id ?? '');
  const [training, setTraining] = useState<TrainingStatus>(currentProgram?.training_status ?? 'not_started');
  const [qualification, setQualification] = useState<TrainingStatus>(currentProgram?.qualification_status ?? 'not_started');
  const [lastTraining, setLastTraining] = useState(currentProgram?.last_training_at ?? '');
  const [nextDue, setNextDue] = useState(currentProgram?.next_qualification_due_at ?? '');
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => {
      if (action.kind === 'create') return createTeacher(universityId, { full_name: name, program_id: programId });
      if (action.kind === 'name') return updateTeacher(action.teacher.id, name);
      const values = {
        training_status: training, qualification_status: qualification,
        last_training_at: lastTraining || null, next_qualification_due_at: nextDue || null,
      };
      if (action.kind === 'add-program') return addTeacherProgram(action.teacher.id, { program_id: programId, ...values });
      return updateTeacherProgram(action.teacher.id, action.program.program_id, values);
    },
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: educationKeys.family(universityId) }); onClose(); },
    onError: (cause) => setError(normalizeApiError(cause).message),
  });
  const title = { create: 'Назначить преподавателя', name: 'Изменить ФИО',
    'add-program': 'Добавить программу преподавателю', program: 'Обучение и квалификация' }[action.kind];
  return <Modal title={title} onClose={onClose}><form className={styles.form} onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
    {action.kind === 'create' || action.kind === 'name'
      ? <label>ФИО преподавателя<Input required value={name} onChange={(event) => setName(event.target.value)} /></label> : null}
    {action.kind === 'create' || action.kind === 'add-program'
      ? <label>Программа<Select required value={programId} onChange={(event) => setProgramId(event.target.value)}>
        <option value="">Выберите программу</option>
        {stats.programs.filter((program) => action.kind === 'create' || !teacher?.teacher_programs.some((row) => row.program_id === program.program_id))
          .map((program) => <option key={program.program_id} value={program.program_id}>{program.program_name}</option>)}
      </Select></label> : null}
    {action.kind === 'program' || action.kind === 'add-program' ? <>
      <label>Обучение преподавателя<Select value={training} onChange={(event) => setTraining(event.target.value as TrainingStatus)}>{Object.entries(statusLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></label>
      <label>Повышение квалификации<Select value={qualification} onChange={(event) => setQualification(event.target.value as TrainingStatus)}>{Object.entries(statusLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></label>
      <label>Последнее обучение<Input type="date" value={lastTraining} onChange={(event) => setLastTraining(event.target.value)} /></label>
      <label>Следующее повышение квалификации<Input type="date" value={nextDue} onChange={(event) => setNextDue(event.target.value)} /></label>
    </> : null}
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
    <div className={styles.actions}><Button variant="ghost" type="button" onClick={onClose}>Отмена</Button><Button variant="primary" type="submit" loading={save.isPending} disabled={save.isPending || (action.kind === 'create' && (!name.trim() || !programId))}>Сохранить</Button></div>
  </form></Modal>;
}

export function TeachersSection({ id }: { id: string }) {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<TeacherAction | null>(null);
  const stats = useQuery({ queryKey: educationKeys.stats(id), queryFn: () => educationStatistics(id), staleTime: 30_000 });
  const teachers = useQuery({ queryKey: educationKeys.teachers(id, page), queryFn: () => listTeachers(id, page), staleTime: 30_000 });
  const canEdit = hasPermission(user, 'university.edit');
  const names = new Map(stats.data?.programs.map((row) => [row.program_id, row.program_name]) ?? []);
  const columns: PassportTableColumn<TeacherRecord>[] = [
    { id: 'name', label: 'Преподаватель', sortable: true, sortValue: (row) => row.full_name, render: (row) => <strong>{row.full_name}</strong> },
    { id: 'programs', label: 'Программа', render: (row) => row.teacher_programs.map((link) => <div key={link.id}>{names.get(link.program_id) ?? 'Программа'}</div>) },
    { id: 'training', label: 'Обучение', render: (row) => row.teacher_programs.map((link) => <div key={link.id}><StatusBadge intent={link.training_status === 'completed' ? 'success' : 'neutral'}>{statusLabels[link.training_status]}</StatusBadge></div>) },
    { id: 'qualification', label: 'Квалификация', render: (row) => row.teacher_programs.map((link) => <div key={link.id}><StatusBadge intent={link.qualification_status === 'completed' ? 'success' : 'neutral'}>{statusLabels[link.qualification_status]}</StatusBadge></div>) },
    { id: 'due', label: 'Следующее повышение', render: (row) => row.teacher_programs.map((link) => <div key={link.id}>{link.next_qualification_due_at ? formatDateRu(link.next_qualification_due_at) : '—'}</div>) },
    ...(canEdit ? [{ id: 'actions', label: 'Действия', render: (row: TeacherRecord) => <div className={styles.actions}>
      <Button variant="ghost" size="s" type="button" onClick={() => setAction({ kind: 'name', teacher: row })}>ФИО</Button>
      {row.teacher_programs.map((link) => <Button key={link.id} variant="ghost" size="s" type="button" onClick={() => setAction({ kind: 'program', teacher: row, program: link })}>Статус: {names.get(link.program_id) ?? 'программа'}</Button>)}
      <Button variant="ghost" size="s" type="button" onClick={() => setAction({ kind: 'add-program', teacher: row })}>Добавить программу</Button>
    </div> }] : []),
  ];
  const mobileFields: PassportMobileField<TeacherRecord>[] = columns.map((column) => ({ label: column.label, render: column.render }));
  return <section className={styles.section} aria-label="Обучение преподавателей">
    <div className={styles.header}><div><h2>Обучение преподавателей</h2><p>Назначения и выполнение этапов по программам ВУЗа</p></div>
      {canEdit && stats.data?.programs.length ? <Button variant="primary" size="s" type="button" onClick={() => setAction({ kind: 'create' })}>Назначить преподавателя</Button> : null}
    </div>
    {stats.data && !stats.data.programs.length ? <p className={styles.meta}>Сначала добавьте программу ВУЗа.</p> : null}
    {teachers.isPending ? <PassportTableSkeleton /> : teachers.isError || !teachers.data
      ? <RouteErrorState compact onRetry={() => void teachers.refetch()} />
      : <PassportDataTable rows={teachers.data.items} columns={columns} mobileFields={mobileFields}
          emptyMessage="Преподаватели не назначены" serverPagination={{ page, pageSize: 20, total: teachers.data.total, onPageChange: setPage }} />}
    {action && stats.data ? <TeacherForm universityId={id} action={action} stats={stats.data} onClose={() => setAction(null)} /> : null}
  </section>;
}
