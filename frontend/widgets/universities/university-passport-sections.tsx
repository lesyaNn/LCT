'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { Button } from '@/shared/ui/rtk/button';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { FilterField } from '@/shared/ui/rtk/filter-field';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Modal } from '@/shared/ui/rtk/modal';
import { EmptyState } from '@/shared/ui/empty-state';
import { Select } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Toast } from '@/shared/ui/rtk/toast';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { licenseStatusIntent, productStatusIntent } from '@/shared/lib/status-semantics';
import {
  getUniversityProducts,
  getUniversityLicenses,
  getUniversityMeetings,
  deleteUniversityMeeting,
  universityProductsQueryKey,
  universityLicensesQueryKey,
  universityMeetingsQueryKey,
  type UniversityProductRow,
  type UniversityProductStatus,
  type UniversityLicenseRow,
  type UniversityLicenseStatus,
  type UniversityMeetingRow,
  type UniversityMeetingType,
} from '@/shared/lib/universities-repository';
import { PassportDataTable, PassportTableSkeleton, type PassportMobileField, type PassportTableColumn } from './passport-data-table';
import { MeetingMutationForm, ProductAssignmentForm } from './passport-mutation-forms';
import { WorkflowMeetingAgenda } from './workflow-meeting-agenda';
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
    { id: 'name', label: 'ИТ-продукт', sortable: true, sortValue: (row) => row.name, render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.version}</span></> },
    { id: 'vendor', label: 'Поставщик', sortable: true, sortValue: (row) => row.vendor, render: (row) => row.vendor },
    { id: 'status', label: 'Статус', sortable: true, sortValue: (row) => productStatusLabels[row.status], render: (row) => <ProductStatusBadge status={row.status} /> },
    { id: 'license', label: 'Лицензия', sortable: true, sortValue: (row) => row.expiresAt, render: (row) => <ProductLicense row={row} /> },
  ];
  const mobileFields: PassportMobileField<UniversityProductRow>[] = [
    { label: 'ИТ-продукт', render: (row) => <><strong className={styles.primaryCell}>{row.name}</strong><span className={styles.secondaryCell}>{row.version}</span></> },
    { label: 'Поставщик', render: (row) => row.vendor },
    { label: 'Статус', render: (row) => <ProductStatusBadge status={row.status} /> },
    { label: 'Лицензия', render: (row) => <ProductLicense row={row} /> },
  ];

  if (query.isPending) return <section className={styles.section} aria-label="ИТ-продукты"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;

  return <section className={styles.section} aria-label="ИТ-продукты">{canAttach ? <SectionToolbar><Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Добавить ИТ-продукт</Button></SectionToolbar> : null}<PassportDataTable rows={query.data} columns={columns} mobileFields={mobileFields} emptyMessage="Нет подключённых ИТ-продуктов" />{assignmentOpen ? <ProductAssignmentForm universityId={id} existingProductIds={query.data.map((product) => product.id)} onClose={() => setAssignmentOpen(false)} onSaved={() => { setAssignmentOpen(false); setSaved(true); }} /> : null}{saved ? <div className={styles.toastViewport}><Toast intent="success" title="ИТ-продукт добавлен" onClose={() => setSaved(false)} /></div> : null}</section>;
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
    { id: 'product', label: 'ИТ-продукт', sortable: true, sortValue: (row) => row.product, render: (row) => <strong className={styles.primaryCell}>{row.product}</strong> },
    { id: 'vendor', label: 'Вендор', sortable: true, sortValue: (row) => row.vendor, render: (row) => row.vendor },
    { id: 'licenseNumber', label: '№ лицензии', render: (row) => row.licenseNumber },
    { id: 'signedAt', label: 'Подписана', sortable: true, sortValue: (row) => row.signedAt, render: (row) => formatDate(row.signedAt) },
    { id: 'expiresAt', label: 'Истекает', sortable: true, sortValue: (row) => row.expiresAt, render: (row) => formatDate(row.expiresAt) },
    { id: 'status', label: 'Статус', render: (row) => <LicenseStatusBadge status={row.status} /> },
    { id: 'transfer', label: 'Передача', render: (row) => row.transfer },
    { id: 'contract', label: 'Договор', render: (row) => <details className={styles.inlineDetails}><summary>Подробнее</summary><span>{row.contract}</span></details> },
  ];
  const mobileFields: PassportMobileField<UniversityLicenseRow>[] = [
    { label: 'ИТ-продукт', render: (row) => <strong className={styles.primaryCell}>{row.product}</strong> },
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
  const canWrite = canAdd;
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
    <WorkflowMeetingAgenda universityId={id} />
    {query.data.items.length ? <ol className={styles.meetingTimeline}>{query.data.items.slice().sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)).map((meeting) => <li className={styles.meetingItem} key={meeting.id}><div className={styles.meetingMarker} aria-hidden="true" /><article className={styles.meetingContent}><div className={styles.meetingMeta}><time dateTime={meeting.occurredAt}>{formatDateTimeRu(meeting.occurredAt)}</time><span className={styles.meetingType}>{meetingTypeLabels[meeting.type]}</span></div><h3>{meeting.subject}</h3><MeetingParticipants participants={meeting.participants} /><details className={styles.meetingDetails}><summary>Итог и следующее действие</summary><p><strong>Итог:</strong> {meeting.outcome}</p><p><strong>Следующее действие:</strong> {meeting.nextAction}{meeting.dueDate ? ` до ${formatDateRu(meeting.dueDate)}` : ''}</p></details><span className={styles.meetingAuthor}>Автор: {meeting.author}</span>{canWrite ? <div className={styles.assignmentActions}><Button variant="ghost" size="s" type="button" onClick={() => setEditor(meeting)}>Изменить</Button><Button variant="ghost" size="s" type="button" onClick={() => setDeleteCandidate(meeting)}>Удалить</Button></div> : null}</article></li>)}</ol> : <EmptyState icon={<Calendar size={20} fill="currentColor" />} title="Встреч пока нет" description={canWrite ? 'Добавьте первую встречу, чтобы зафиксировать взаимодействие.' : 'Встречи появятся после их добавления на сервере.'} headingLevel={3} />}
    {query.data.total > 20 ? <div className={styles.sectionToolbar}><span>Страница {page} из {Math.ceil(query.data.total / 20)}</span><div className={styles.toolbarControls}><Button variant="ghost" size="s" type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>Назад</Button><Button variant="ghost" size="s" type="button" disabled={page * 20 >= query.data.total} onClick={() => setPage(page + 1)}>Далее</Button></div></div> : null}
    {editor !== undefined ? <MeetingMutationForm universityId={id} meeting={editor} onClose={() => setEditor(undefined)} onSaved={() => { setEditor(undefined); setMessage('Встреча сохранена.'); }} /> : null}
    {deleteCandidate ? <Modal title="Удалить встречу?" onClose={() => { if (!remove.isPending) setDeleteCandidate(null); }}><p>Встреча «{deleteCandidate.subject}» будет удалена без возможности восстановления.</p><div className={styles.assignmentActions}><Button variant="ghost" type="button" disabled={remove.isPending} onClick={() => setDeleteCandidate(null)}>Отмена</Button><Button variant="danger" type="button" loading={remove.isPending} disabled={remove.isPending} onClick={() => remove.mutate(deleteCandidate.id)}>Удалить</Button></div></Modal> : null}
    {message ? <div className={styles.toastViewport}><Toast intent={remove.isError ? 'error' : 'success'} title={message} onClose={() => setMessage(null)} /></div> : null}
  </section>;
}

export { LicensesSection, DocumentsSection, MeetingsSection };
