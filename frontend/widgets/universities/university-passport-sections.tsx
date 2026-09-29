'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import Mail from '@atomaro/icons/24/communication/Mail';
import Phone from '@atomaro/icons/24/technology/Phone';
import { Button } from '@/shared/ui/rtk/button';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { FilterField } from '@/shared/ui/rtk/filter-field';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { Modal } from '@/shared/ui/rtk/modal';
import { EmptyState } from '@/shared/ui/empty-state';
import { Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Toast } from '@/shared/ui/rtk/toast';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { adminUsersQueryKeys, assignUniversityResponsible, listResponsibleCandidates } from '@/shared/lib/users-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { licenseStatusIntent, productStatusIntent } from '@/shared/lib/status-semantics';
import {
  getUniversityProducts,
  getUniversityLicenses,
  getUniversityMeetings,
  deleteUniversityMeeting,
  getUniversityResponsibles,
  universityProductsQueryKey,
  universityLicensesQueryKey,
  universityMeetingsQueryKey,
  universityPassportQueryKey,
  universityResponsiblesQueryKey,
  type UniversityProductRow,
  type UniversityProductStatus,
  type UniversityLicenseRow,
  type UniversityLicenseStatus,
  type UniversityMeetingRow,
  type UniversityMeetingType,
} from '@/shared/lib/universities-repository';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from './passport-data-table';
import { MeetingMutationForm, ProductAssignmentForm } from './passport-mutation-forms';
import styles from './university-passport-sections.module.css';
import { PassportDocumentsSection } from './passport-documents-section';

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

function ProductStatusBadge({ status }: { status: UniversityProductStatus }) {
  return <StatusBadge intent={productStatusIntent[status]}>{productStatusLabels[status]}</StatusBadge>;
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

  return <section className={styles.section} aria-label="Продукты">{canAttach ? <SectionToolbar><Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Добавить продукт</Button></SectionToolbar> : null}<PassportDataTable rows={query.data} columns={columns} mobileFields={mobileFields} emptyMessage="Нет подключённых продуктов" />{assignmentOpen ? <ProductAssignmentForm universityId={id} existingProductIds={query.data.map((product) => product.id)} onClose={() => setAssignmentOpen(false)} onSaved={() => { setAssignmentOpen(false); setSaved(true); }} /> : null}{saved ? <div className={styles.toastViewport}><Toast intent="success" title="Продукт добавлен" onClose={() => setSaved(false)} /></div> : null}</section>;
}

export { ProductsSection };

const licenseStatusLabels: Record<UniversityLicenseStatus, string> = { active: 'Действует', expires_soon: 'Скоро истекает', expired: 'Просрочена' };
const meetingTypeLabels: Record<UniversityMeetingType, string> = { online: 'Онлайн', offline: 'Очно', phone: 'Телефон', email: 'Email' };

function LicenseStatusBadge({ status }: { status: UniversityLicenseStatus }) {
  return <StatusBadge intent={licenseStatusIntent[status]}>{licenseStatusLabels[status]}</StatusBadge>;
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
  return <section className={styles.section} aria-label="Лицензии"><FilterToolbar embedded compact label="Фильтры лицензий" controls={() => <FilterField label="Статус"><Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as UniversityLicenseStatus | 'all')}><option value="all">Все статусы</option>{Object.entries(licenseStatusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</Select></FilterField>} activeFilters={statusFilter === 'all' ? [] : [{ id: 'status', label: `Статус: ${licenseStatusLabels[statusFilter]}`, onRemove: () => setStatusFilter('all') }]} mobileCount={statusFilter === 'all' ? 0 : 1} /><PassportDataTable rows={rows} columns={columns} mobileFields={mobileFields} emptyMessage="Лицензии пока не добавлены" /></section>;
}

function DocumentsSection({ id }: { id: string }) {
  return <PassportDocumentsSection id={id} />;
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
    {canWrite ? <SectionToolbar><Button variant="primary" size="s" type="button" onClick={() => setEditor(null)}><Calendar size={16} fill="currentColor" />Добавить встречу</Button></SectionToolbar> : null}
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
  return <><section className={styles.section} aria-label="Ответственные">{canEdit ? <SectionToolbar><Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Сменить ответственного</Button></SectionToolbar> : null}{query.data.length ? <div className={styles.responsiblesGrid}>{query.data.map((person) => <article className={styles.responsibleCard} key={person.id}><Avatar initials={person.initials} size="m" /><div className={styles.responsibleInfo}><h3>{person.name}</h3><p>{person.role}</p><a href={`mailto:${person.email}`}><Mail size={16} fill="currentColor" />{person.email}</a><a href={`tel:${person.phone.replace(/[^+\d]/g, '')}`}><Phone size={16} fill="currentColor" />{person.phone}</a></div>{person.isPrimary ? <StatusBadge intent="brand">Основной</StatusBadge> : null}</article>)}</div> : <EmptyState icon={<Mail size={20} fill="currentColor" />} title="Ответственные не назначены" description="Контактные лица появятся здесь после назначения." headingLevel={3} />}</section>{assignmentOpen ? <ResponsibleAssignmentDrawer id={id} currentName={currentName} onClose={() => setAssignmentOpen(false)} onSuccess={() => { setAssignmentOpen(false); setToast(true); }} /> : null}{toast ? <Toast intent="success" title="Ответственный изменён" message="Паспорт, история и связанные списки обновляются." onClose={() => setToast(false)} /> : null}</>;
}

export { LicensesSection, DocumentsSection, MeetingsSection, ResponsiblesSection };
