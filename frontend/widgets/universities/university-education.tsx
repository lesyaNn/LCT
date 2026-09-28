'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { addCertificate, addQualification, addTeacherProgram, createLearner, createTeacher, deleteLearner, deleteTeacher, educationKeys, integrationCapabilities, learnerSummary, listLearners, listTeachers, removeTeacherChild, syncDemoLms, updateLearner, updateTeacher, type LearnerCreate, type LearnerRecord, type LearnerStatus, type TeacherRecord } from '@/shared/lib/education-repository';
import { formatDateRu } from '@/shared/lib/formatters';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from './passport-data-table';
import { Button } from '@/shared/ui/rtk/button';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { FilterField } from '@/shared/ui/rtk/filter-field';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './university-education.module.css';

const statusNames: Record<LearnerStatus, string> = {
  active: 'Обучается', graduated: 'Завершил', expelled: 'Отчислен', academic_leave: 'Академический отпуск',
};
const emptyLearner: LearnerCreate = { external_id: '', program_id: '', full_name: '', group_name: null, status: 'active', started_at: '', finished_at: null };

function Metric({ label, value }: { label: string; value: number }) {
  return <div className={styles.metric}><strong>{value}</strong><span>{label}</span></div>;
}

function LearnerForm({ universityId, initial, programs, onClose }: { universityId: string; initial?: LearnerRecord; programs: { program_id: string; program_name: string }[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState<LearnerCreate>(initial ? {
    external_id: initial.external_id, program_id: initial.program_id, full_name: initial.full_name,
    group_name: initial.group_name, status: initial.status, started_at: initial.started_at,
    finished_at: initial.finished_at,
  } : emptyLearner);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => initial ? updateLearner(initial.id, value) : createLearner(universityId, value),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: educationKeys.family(universityId) }); onClose(); },
    onError: (cause) => setError(normalizeApiError(cause).message),
  });
  return <Modal title={initial ? 'Изменить обучающегося' : 'Добавить обучающегося'} onClose={onClose}><form className={styles.form} onSubmit={(event) => { event.preventDefault(); setError(''); save.mutate(); }}>
    <label>Внешний ID<Input value={value.external_id} disabled={Boolean(initial)} required onChange={(event) => setValue({ ...value, external_id: event.target.value })} /></label>
    <label>ФИО<Input value={value.full_name} required onChange={(event) => setValue({ ...value, full_name: event.target.value })} /></label>
    <label>Программа<Select value={value.program_id} required onChange={(event) => setValue({ ...value, program_id: event.target.value })}><option value="">Выберите программу</option>{programs.map((item) => <option key={item.program_id} value={item.program_id}>{item.program_name}</option>)}</Select></label>
    <label>Поток / группа<Input value={value.group_name ?? ''} onChange={(event) => setValue({ ...value, group_name: event.target.value || null })} /></label>
    <label>Статус<Select value={value.status} onChange={(event) => setValue({ ...value, status: event.target.value as LearnerStatus })}>{Object.entries(statusNames).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</Select></label>
    <label>Дата начала<Input type="date" value={value.started_at} required onChange={(event) => setValue({ ...value, started_at: event.target.value })} /></label>
    <label>Дата завершения<Input type="date" value={value.finished_at ?? ''} onChange={(event) => setValue({ ...value, finished_at: event.target.value || null })} /></label>
    {error ? <p className={styles.error} role="alert">{error}</p> : null}<div className={styles.actions}><Button variant="ghost" type="button" onClick={onClose}>Отмена</Button><Button variant="primary" type="submit" loading={save.isPending} disabled={save.isPending || !value.external_id || !value.full_name || !value.program_id || !value.started_at}>Сохранить</Button></div>
  </form></Modal>;
}

export function StudentsSection({ id }: { id: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [programId, setProgramId] = useState('');
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState<LearnerRecord | 'new' | null>(null);
  const [error, setError] = useState('');
  const summary = useQuery({ queryKey: educationKeys.summary(id), queryFn: () => learnerSummary(id), staleTime: 30_000 });
  const learners = useQuery({ queryKey: educationKeys.learners(id, page, programId, status), queryFn: () => listLearners(id, page, programId, status), staleTime: 30_000 });
  const capabilities = useQuery({ queryKey: ['integrations', 'capabilities'], queryFn: integrationCapabilities, staleTime: 60_000 });
  const sync = useMutation({ mutationFn: () => syncDemoLms(id), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: educationKeys.family(id) }); setError(''); }, onError: (cause) => setError(normalizeApiError(cause).message) });
  const remove = useMutation({ mutationFn: deleteLearner, onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: educationKeys.family(id) }); }, onError: (cause) => setError(normalizeApiError(cause).message) });
  const canEdit = hasPermission(user, 'university.edit');
  const programNames = new Map(summary.data?.programs.map((program) => [program.program_id, program.program_name]) ?? []);
  const columns: PassportTableColumn<LearnerRecord>[] = [
    { id: 'name', label: 'Обучающийся', sortable: true, sortValue: (row) => row.full_name, render: (row) => <strong>{row.full_name}</strong> },
    { id: 'program', label: 'Программа', render: (row) => programNames.get(row.program_id) ?? '—' },
    { id: 'flow', label: 'Поток', render: (row) => row.group_name ?? '—' },
    { id: 'status', label: 'Статус', render: (row) => <StatusBadge intent={row.status === 'active' ? 'success' : 'neutral'}>{statusNames[row.status]}</StatusBadge> },
    { id: 'source', label: 'Источник', render: (row) => row.source === 'lms' ? 'LMS' : row.source === 'mock_lms' ? 'LMS (TEST/DEMO)' : 'Ручной ввод' },
    { id: 'started', label: 'Начало', render: (row) => formatDateRu(row.started_at) },
    { id: 'actions', label: 'Действия', render: (row) => canEdit ? <div className={styles.actions}><Button variant="ghost" size="s" type="button" onClick={() => setEditing(row)}>Изменить</Button><Button variant="ghost" size="s" type="button" onClick={() => { if (window.confirm('Удалить запись обучающегося?')) remove.mutate(row.id); }}>Удалить</Button></div> : null },
  ];
  const mobileFields: PassportMobileField<LearnerRecord>[] = columns.filter((column) => column.id !== 'started').map((column) => ({ label: column.label, render: column.render }));
  return <section className={styles.section} aria-label="Обучающиеся"><div className={styles.header}><h2>Обучающиеся</h2>{canEdit ? <div className={styles.actions}>{capabilities.data?.demo_lms_enabled ? <Button variant="ghost" size="s" type="button" loading={sync.isPending} onClick={() => sync.mutate()}>Синхронизировать тестовый LMS</Button> : null}<Button variant="primary" size="s" type="button" onClick={() => setEditing('new')}>Добавить</Button></div> : null}</div>
    {summary.isError ? <RouteErrorState compact onRetry={() => void summary.refetch()} /> : summary.data ? <div className={styles.metrics}><Metric label="Обучающихся" value={summary.data.learners} /><Metric label="Обучаются" value={summary.data.active_learners} /><Metric label="Потоков" value={summary.data.flows} /></div> : null}
    <FilterToolbar embedded label="Фильтры обучающихся" activeFilters={[...(programId ? [{ id: 'program', label: `Программа: ${programNames.get(programId) ?? ''}`, onRemove: () => { setProgramId(''); setPage(1); } }] : []), ...(status ? [{ id: 'status', label: `Статус: ${statusNames[status as LearnerStatus]}`, onRemove: () => { setStatus(''); setPage(1); } }] : [])]} controls={() => <><FilterField label="Программа"><Select value={programId} onChange={(event) => { setProgramId(event.target.value); setPage(1); }}><option value="">Все программы</option>{summary.data?.programs.map((program) => <option value={program.program_id} key={program.program_id}>{program.program_name}</option>)}</Select></FilterField><FilterField label="Статус"><Select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">Все статусы</option>{Object.entries(statusNames).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</Select></FilterField></>} onReset={() => { setProgramId(''); setStatus(''); setPage(1); }} resetDisabled={!programId && !status} />
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
    {learners.isPending ? <PassportTableSkeleton /> : learners.isError || !learners.data ? <RouteErrorState compact onRetry={() => void learners.refetch()} /> : <PassportDataTable rows={learners.data.items} columns={columns} mobileFields={mobileFields} emptyMessage="Обучающиеся не найдены" serverPagination={{ page, pageSize: 20, total: learners.data.total, onPageChange: setPage }} />}
    {editing ? <LearnerForm universityId={id} initial={editing === 'new' ? undefined : editing} programs={summary.data?.programs ?? []} onClose={() => setEditing(null)} /> : null}
  </section>;
}

type TeacherAction = 'create' | 'edit' | 'qualification' | 'certificate' | 'program';
function TeacherForm({ universityId, teacher, action, programs, onClose }: { universityId: string; teacher?: TeacherRecord; action: TeacherAction; programs: { program_id: string; program_name: string }[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(teacher?.full_name ?? ''); const [email, setEmail] = useState(teacher?.email ?? ''); const [position, setPosition] = useState(teacher?.position ?? '');
  const [title, setTitle] = useState(''); const [issuer, setIssuer] = useState(''); const [date, setDate] = useState(''); const [expires, setExpires] = useState(''); const [programId, setProgramId] = useState(''); const [mandatory, setMandatory] = useState(false); const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => {
      if (action === 'create') return createTeacher(universityId, { full_name: name, email, phone: null, position });
      if (!teacher) throw new Error('Преподаватель не выбран');
      if (action === 'edit') return updateTeacher(teacher.id, { full_name: name, email, position });
      if (action === 'qualification') return addQualification(teacher.id, { qualification_name: title, obtained_at: date, expires_at: expires || null, document_ref: null });
      if (action === 'certificate') return addCertificate(teacher.id, { certificate_name: title, issued_by: issuer, issued_at: date, expires_at: expires || null, is_mandatory: mandatory, program_id: programId || null, document_ref: null });
      return addTeacherProgram(teacher.id, { program_id: programId, can_teach: true, assigned_at: date });
    },
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: educationKeys.family(universityId) }); onClose(); },
    onError: (cause) => setError(normalizeApiError(cause).message),
  });
  const heading = { create: 'Добавить преподавателя', edit: 'Изменить преподавателя', qualification: 'Добавить квалификацию', certificate: 'Добавить сертификат', program: 'Связать с программой' }[action];
  return <Modal title={heading} onClose={onClose}><form className={styles.form} onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
    {action === 'create' || action === 'edit' ? <><label>ФИО<Input value={name} required onChange={(event) => setName(event.target.value)} /></label><label>Email<Input type="email" value={email} required onChange={(event) => setEmail(event.target.value)} /></label><label>Должность<Input value={position} onChange={(event) => setPosition(event.target.value)} /></label></> : null}
    {action === 'qualification' || action === 'certificate' ? <label>Название<Input value={title} required onChange={(event) => setTitle(event.target.value)} /></label> : null}
    {action === 'certificate' ? <><label>Кем выдан<Input value={issuer} onChange={(event) => setIssuer(event.target.value)} /></label><label><input type="checkbox" checked={mandatory} onChange={(event) => setMandatory(event.target.checked)} /> Обязательный</label></> : null}
    {action === 'program' || action === 'certificate' ? <label>Программа<Select value={programId} required={action === 'program'} onChange={(event) => setProgramId(event.target.value)}><option value="">{action === 'program' ? 'Выберите программу' : 'Без привязки'}</option>{programs.map((program) => <option value={program.program_id} key={program.program_id}>{program.program_name}</option>)}</Select></label> : null}
    {action !== 'create' && action !== 'edit' ? <label>{action === 'program' ? 'Дата назначения' : action === 'certificate' ? 'Дата выдачи' : 'Дата получения'}<Input type="date" value={date} required onChange={(event) => setDate(event.target.value)} /></label> : null}
    {action === 'qualification' || action === 'certificate' ? <label>Действует до<Input type="date" value={expires} onChange={(event) => setExpires(event.target.value)} /></label> : null}
    {error ? <p className={styles.error} role="alert">{error}</p> : null}<div className={styles.actions}><Button variant="ghost" type="button" onClick={onClose}>Отмена</Button><Button variant="primary" type="submit" loading={save.isPending} disabled={save.isPending}>Сохранить</Button></div>
  </form></Modal>;
}

export function TeachersSection({ id }: { id: string }) {
  const { user } = useAuth(); const [page, setPage] = useState(1); const [selected, setSelected] = useState<TeacherRecord | null>(null); const [action, setAction] = useState<TeacherAction | null>(null);
  const [error, setError] = useState(''); const queryClient = useQueryClient();
  const teachers = useQuery({ queryKey: educationKeys.teachers(id, page), queryFn: () => listTeachers(id, page), staleTime: 30_000 });
  const summary = useQuery({ queryKey: educationKeys.summary(id), queryFn: () => learnerSummary(id), staleTime: 30_000 });
  const canEdit = hasPermission(user, 'university.edit');
  const remove = useMutation({ mutationFn: (teacherId: string) => deleteTeacher(teacherId), onSuccess: async () => { setSelected(null); await queryClient.invalidateQueries({ queryKey: educationKeys.family(id) }); }, onError: (cause) => setError(normalizeApiError(cause).message) });
  const removeChild = useMutation({ mutationFn: ({ kind, childId }: { kind: 'qualifications' | 'certificates' | 'programs'; childId: string }) => {
    if (!selected) throw new Error('Преподаватель не выбран');
    return removeTeacherChild(selected.id, kind, childId);
  }, onSuccess: async (updated) => { setSelected(updated); await queryClient.invalidateQueries({ queryKey: educationKeys.family(id) }); }, onError: (cause) => setError(normalizeApiError(cause).message) });
  const childRemoveButton = (kind: 'qualifications' | 'certificates' | 'programs', childId: string) => canEdit ? <Button variant="ghost" size="s" type="button" disabled={removeChild.isPending} onClick={() => { if (window.confirm('Удалить запись?')) removeChild.mutate({ kind, childId }); }}>Удалить</Button> : null;
  const columns: PassportTableColumn<TeacherRecord>[] = [
    { id: 'name', label: 'Преподаватель', sortable: true, sortValue: (row) => row.full_name, render: (row) => <strong>{row.full_name}</strong> },
    { id: 'position', label: 'Должность', render: (row) => row.position || '—' },
    { id: 'programs', label: 'Программы', render: (row) => row.teacher_programs.length },
    { id: 'qualifications', label: 'Квалификации', render: (row) => row.qualifications.length },
    { id: 'certificates', label: 'Сертификаты', render: (row) => row.certificates.length },
    { id: 'actions', label: 'Действия', render: (row) => <Button variant="ghost" size="s" type="button" onClick={() => setSelected(row)}>Открыть</Button> },
  ];
  const mobileFields: PassportMobileField<TeacherRecord>[] = columns.map((column) => ({ label: column.label, render: column.render }));
  return <section className={styles.section} aria-label="Преподаватели"><div className={styles.header}><h2>Преподаватели</h2>{canEdit ? <Button variant="primary" size="s" type="button" onClick={() => setAction('create')}>Добавить преподавателя</Button> : null}</div>
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
    {teachers.isPending ? <PassportTableSkeleton /> : teachers.isError || !teachers.data ? <RouteErrorState compact onRetry={() => void teachers.refetch()} /> : <PassportDataTable rows={teachers.data.items} columns={columns} mobileFields={mobileFields} emptyMessage="Преподаватели не добавлены" serverPagination={{ page, pageSize: 20, total: teachers.data.total, onPageChange: setPage }} />}
    {selected && !action ? <Modal title={selected.full_name} onClose={() => setSelected(null)}><div className={styles.teacherDetails}><p>{selected.position || 'Должность не указана'} · {selected.email}</p><h3>Программы</h3><ul>{selected.teacher_programs.map((item) => <li key={item.id}>{summary.data?.programs.find((program) => program.program_id === item.program_id)?.program_name ?? 'Программа'} · {item.can_teach ? 'может преподавать' : 'не допущен'} {childRemoveButton('programs', item.id)}</li>)}</ul><h3>Квалификации</h3><ul>{selected.qualifications.map((item) => <li key={item.id}>{item.qualification_name} · {formatDateRu(item.obtained_at)}{item.expires_at ? ` — ${formatDateRu(item.expires_at)}` : ''} {childRemoveButton('qualifications', item.id)}</li>)}</ul><h3>Сертификаты</h3><ul>{selected.certificates.map((item) => <li key={item.id}>{item.certificate_name} · {formatDateRu(item.issued_at)}{item.expires_at ? ` — ${formatDateRu(item.expires_at)}` : ''} {childRemoveButton('certificates', item.id)}</li>)}</ul>{canEdit ? <div className={styles.teacherActions}>{(['edit', 'qualification', 'certificate', 'program'] as const).map((kind) => <Button key={kind} variant="ghost" size="s" type="button" onClick={() => setAction(kind)}>{kind === 'edit' ? 'Изменить' : kind === 'qualification' ? 'Квалификация' : kind === 'certificate' ? 'Сертификат' : 'Программа'}</Button>)}<Button variant="ghost" size="s" type="button" disabled={remove.isPending} onClick={() => { if (window.confirm('Удалить преподавателя и его записи?')) remove.mutate(selected.id); }}>Удалить преподавателя</Button></div> : null}</div></Modal> : null}
    {action ? <TeacherForm universityId={id} teacher={selected ?? undefined} action={action} programs={summary.data?.programs ?? []} onClose={() => { setAction(null); setSelected(null); }} /> : null}
  </section>;
}
