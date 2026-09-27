'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Edit from '@atomaro/icons/24/editor/Edit';
import Trash from '@atomaro/icons/24/action/Trash';
import { useAuth } from '@/shared/auth/AuthProvider';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import {
  agreementStatusLabels,
  canMutateCatalog,
  catalogDefinition,
  catalogDefinitions,
  catalogDeleteBlockers,
  catalogQueryKeys,
  createCatalogItem,
  deleteCatalogItem,
  getCatalogItem,
  getCatalogReferenceData,
  listCatalogItems,
  relatedCatalogQueryKeys,
  updateCatalogItem,
  type AgreementCatalogItem,
  type AgreementKind,
  type CatalogContact,
  type CatalogInput,
  type CatalogItem,
  type CatalogListQuery,
  type CatalogType,
  transferStatusLabels,
} from '@/shared/lib/catalogs-repository';
import { Button, ButtonLink } from '@/shared/ui/rtk/button';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { TabbedSurface } from '@/shared/ui/rtk/tabbed-surface';
import { EmptyState } from '@/shared/ui/empty-state';
import { Input } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { TableSkeleton } from '@/shared/ui/skeleton';
import { CatalogFormModal } from './catalog-form-modal';
import styles from './catalogs-page.module.css';

const pageSize = 8;

function agreementSingularLabel(item: CatalogItem): string {
  return item.type === 'agreements' ? (item.kind === 'contracts' ? 'Договор' : 'Лицензия') : 'Запись';
}

/** Entities whose detail endpoint also exposes vendor contacts. */
const contactCatalogTypes: ReadonlyArray<CatalogType> = ['products', 'vendors'];

function secondaryFields(item: CatalogItem, universityNames: ReadonlyMap<string, string>): Array<{ label: string; value: string }> {
  if (item.type === 'universities') return [{ label: 'Город', value: item.city || '—' }];
  if (item.type === 'directions') return [{ label: 'Код', value: item.code }];
  if (item.type === 'programs') return [{ label: 'Направление', value: item.directionName || '—' }, { label: 'Описание', value: item.description || '—' }];
  if (item.type === 'vendors') return [];
  if (item.type === 'products') return [{ label: 'Вендор', value: item.vendorName || '—' }, { label: 'Программа', value: item.programName || '—' }, { label: 'Версия', value: item.version || '—' }];
  if (item.type === 'agreements') return agreementFields(item);
  return [{ label: 'Email', value: item.email }, { label: 'Роль', value: item.role || '—' }, { label: 'ВУЗы', value: item.universityIds.length ? item.universityIds.map((id) => universityNames.get(id) ?? '—').join(', ') : 'Нет' }];
}

/** Both agreement kinds lead with the university, as required by the import template. */
function agreementFields(item: AgreementCatalogItem): Array<{ label: string; value: string }> {
  const base = [
    { label: 'ВУЗ', value: item.universityName || '—' },
    { label: 'Вендор', value: item.vendorName || '—' },
  ];
  if (item.kind === 'contracts') {
    return [
      ...base,
      { label: 'Продукт', value: item.productName || '—' },
      { label: 'Подписан', value: item.signedAt || '—' },
      { label: 'Окончание', value: item.expiresAt || 'Бессрочно' },
      { label: 'Статус', value: agreementStatusLabels[item.status] },
      { label: 'Передача', value: transferStatusLabels[item.transferStatus] },
      { label: 'Лицензий', value: String(item.licenseCount) },
    ];
  }
  return [
    ...base,
    { label: 'Продукт', value: item.productName || '—' },
    { label: 'Договор', value: item.contractNumber || '—' },
    { label: 'Программа', value: item.programName || '—' },
    { label: 'Подписан', value: item.signedAt || '—' },
    { label: 'Окончание', value: item.expiresAt || 'Бессрочно' },
    { label: 'Статус', value: agreementStatusLabels[item.status] },
    { label: 'Передача', value: transferStatusLabels[item.transferStatus] },
  ];
}

function tableHeaders(type: CatalogType, kind: AgreementKind): string[] {
  if (type === 'universities') return ['Название', 'Город'];
  if (type === 'directions') return ['Название', 'Код'];
  if (type === 'programs') return ['Название', 'Направление', 'Описание'];
  if (type === 'vendors') return ['Название'];
  if (type === 'products') return ['Название', 'Вендор', 'Программа', 'Версия'];
  if (type === 'agreements') {
    return kind === 'contracts'
      ? ['Номер договора', 'ВУЗ', 'Вендор', 'Продукт', 'Подписан', 'Окончание', 'Статус', 'Передача', 'Лицензий']
      : ['Номер лицензии', 'ВУЗ', 'Вендор', 'Продукт', 'Договор', 'Программа', 'Подписан', 'Окончание', 'Статус', 'Передача'];
  }
  return ['ФИО', 'Email', 'Роль', 'ВУЗы'];
}

function hasContacts(item: CatalogItem): boolean {
  return contactCatalogTypes.includes(item.type);
}

function itemContacts(item: CatalogItem | undefined): CatalogContact[] | undefined {
  return item && (item.type === 'products' || item.type === 'vendors') ? item.contacts : undefined;
}

function CatalogActions({ item, canWrite, busy, onEdit, onDelete }: { item: CatalogItem; canWrite: boolean; busy: boolean; onEdit: () => void; onDelete: () => void }) {
  const writeHint = canWrite ? null : 'Изменять каталоги может только администратор или менеджер.';
  const editLabel = `Изменить ${item.name}`;
  const deleteLabel = `Удалить ${item.name}`;
  return <div className={styles.rowActions}>
    <Tooltip content={writeHint ?? editLabel}><IconButton icon={<Edit size={18} fill="currentColor" />} label={editLabel} disabled={!canWrite || busy} onClick={onEdit} /></Tooltip>
    <Tooltip content={writeHint ?? deleteLabel}><IconButton data-testid="catalog-delete" icon={<Trash size={18} fill="currentColor" />} label={deleteLabel} disabled={!canWrite || busy} onClick={onDelete} /></Tooltip>
  </div>;
}

function CatalogTable({ type, kind, items, canWrite, busyId, universityNames, onEdit, onDelete, onContacts }: { type: CatalogType; kind: AgreementKind; items: CatalogItem[]; canWrite: boolean; busyId?: string; universityNames: ReadonlyMap<string, string>; onEdit: (item: CatalogItem) => void; onDelete: (item: CatalogItem) => void; onContacts: (item: CatalogItem) => void }) {
  const headers = tableHeaders(type, kind);
  const busy = (item: CatalogItem) => busyId === item.id;
  const actions = (item: CatalogItem) => <div className={styles.rowActions}>{hasContacts(item) ? <Button type="button" variant="ghost" size="s" onClick={() => onContacts(item)}>Контакты</Button> : null}<CatalogActions item={item} canWrite={canWrite} busy={busy(item)} onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} /></div>;
  return <TableShell ariaLabel={`Каталог «${catalogDefinition(type).label}»`}>
    <div className={headers.length > 2 ? styles.desktopTable : `${styles.desktopTable} ${styles.compactTable}`}><table><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}<th>Действия</th></tr></thead><tbody>{items.map((item) => <tr data-testid={`catalog-row-${item.id}`} key={item.id}><td><button className={styles.nameButton} type="button" disabled={!canWrite} onClick={() => onEdit(item)}>{item.name}</button></td>{secondaryFields(item, universityNames).map((field) => <td key={field.label}>{field.value}</td>)}<td>{actions(item)}</td></tr>)}</tbody></table></div>
    <div className={styles.mobileList}>{items.map((item) => <article className={styles.catalogCard} key={item.id}><div className={styles.cardTop}><strong>{item.name}</strong></div><dl>{secondaryFields(item, universityNames).map((field) => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>{hasContacts(item) ? <Button type="button" variant="ghost" size="s" onClick={() => onContacts(item)}>Контакты</Button> : null}<CatalogActions item={item} canWrite={canWrite} busy={busy(item)} onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} /></article>)}</div>
  </TableShell>;
}

function ContactList({ contacts }: { contacts?: CatalogContact[] }) {
  if (!contacts?.length) return <p>Контакты не указаны.</p>;
  return <>{contacts.map((contact) => <dl key={contact.id}><dt><strong>{contact.fullName}</strong></dt><dd>{contact.email} · {contact.phone || 'телефон не указан'} · {contact.communicationMethod || 'способ связи не указан'}</dd></dl>)}</>;
}

export function CatalogsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [type, setType] = useState<CatalogType>('universities');
  // The combined tab renders one of two real resources at a time.
  const [agreementKind, setAgreementKind] = useState<AgreementKind>('contracts');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [formItem, setFormItem] = useState<CatalogItem | null | undefined>(undefined);
  const [contactsItem, setContactsItem] = useState<CatalogItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CatalogItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);
  const canWrite = canMutateCatalog(user?.role);

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedSearch(search), 250); return () => window.clearTimeout(timer); }, [search]);

  const listQuery: CatalogListQuery = useMemo(() => ({ type, search: debouncedSearch, page, pageSize, ...(type === 'agreements' ? { agreementKind } : {}) }), [agreementKind, debouncedSearch, page, type]);
  const query = useQuery({ queryKey: catalogQueryKeys.list(type, listQuery), queryFn: ({ signal }) => listCatalogItems(listQuery, signal), placeholderData: (previous) => previous, staleTime: 15_000 });
  const referencesQuery = useQuery({ queryKey: catalogQueryKeys.references, queryFn: ({ signal }) => getCatalogReferenceData(signal), staleTime: 5 * 60_000 });
  const contactsQuery = useQuery({ queryKey: contactsItem ? catalogQueryKeys.detail(contactsItem.type, contactsItem.id) : queryKeys.catalogs.contactsIdle, queryFn: ({ signal }) => getCatalogItem(contactsItem!.type, contactsItem!.id, signal), enabled: Boolean(contactsItem) });
  const pageCount = Math.max(1, Math.ceil((query.data?.total ?? 0) / pageSize));

  const invalidateRelated = async (itemType: CatalogType, id?: string) => {
    await Promise.all(relatedCatalogQueryKeys(itemType, id).map((queryKey) => queryClient.invalidateQueries({ queryKey })));
  };

  const saveMutation = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CatalogInput }) => id ? updateCatalogItem(id, input) : createCatalogItem(input),
    onSuccess: async (saved, variables) => {
      await invalidateRelated(saved.type, saved.id);
      setFormItem(undefined);
      setToast({ intent: 'success', title: variables.id ? 'Запись сохранена' : 'Запись добавлена', message: saved.name || (saved.type === 'agreements' ? agreementSingularLabel(saved) : undefined) });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: ({ item }: { item: CatalogItem }) => deleteCatalogItem(item.type, item.id, item.type === 'agreements' ? item.kind : undefined),
    onSuccess: async (_result, { item }) => {
      await invalidateRelated(item.type, item.id);
      setDeleteTarget(null);
      setDeleteError(null);
      setToast({ intent: 'success', title: 'Запись удалена', message: item.name });
    },
    onError: (cause, { item }) => {
      const normalized = normalizeApiError(cause, { fallbackMessage: 'Не удалось удалить запись.' });
      setDeleteError(normalized.status === 409 ? catalogDeleteBlockers[item.type] : normalized.message);
    },
  });

  const chooseType = (next: CatalogType) => { setType(next); setSearch(''); setDebouncedSearch(''); setPage(1); setFormItem(undefined); setDeleteTarget(null); setDeleteError(null); setContactsItem(null); };
  const chooseKind = (next: AgreementKind) => { setAgreementKind(next); setSearch(''); setDebouncedSearch(''); setPage(1); setFormItem(undefined); setDeleteTarget(null); setDeleteError(null); };
  const definition = catalogDefinition(type);
  const references = referencesQuery.data ?? { vendors: [], universities: [], products: [], directions: [], programs: [], responsibles: [], contracts: [] };
  // Responsible rows show university names, resolved from the already loaded
  // reference list instead of another request per row.
  const universityNames = new Map(references.universities.map((university) => [university.id, university.name]));
  const referencesRequired = type === 'products' || type === 'programs' || type === 'responsibles' || type === 'agreements';
  const formReferencesReady = !referencesRequired || (!referencesQuery.isPending && !referencesQuery.isError);
  const addButton = <Button data-testid="catalog-add" type="button" variant="primary" disabled={!canWrite || !formReferencesReady} onClick={() => setFormItem(null)}>Добавить</Button>;
  const busyId = deleteMutation.isPending ? deleteMutation.variables?.item.id : undefined;

  return <div className={styles.page}>
    <header className={styles.pageHeader}><div><h1>Управление каталогами</h1><p>Управляйте основными справочниками CRM.</p></div></header>
    <TabbedSurface tabs={<Tabs items={catalogDefinitions} activeId={type} onChange={(id) => chooseType(id as CatalogType)} label="Каталоги" prefix="catalog-tab" />}>
      <div data-testid="catalog-tabs">
        <section id="catalog-panel" role="tabpanel" aria-labelledby={`catalog-tab-${type}`} className={styles.panel}>
          <FilterToolbar
            embedded
            label="Фильтры каталога"
            activeFilters={search ? [{ id: 'search', label: `Поиск: ${search}`, onRemove: () => { setSearch(''); setPage(1); } }] : []}
            controls={() => <><label className={styles.search}><span>Поиск</span><Input type="search" value={search} placeholder={definition.searchPlaceholder} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label><div className={styles.actions}>{canWrite ? addButton : <Tooltip content="На текущем этапе каталоги подключены только для чтения.">{addButton}</Tooltip>}<ButtonLink href="/admin/import" variant="orange">Импорт</ButtonLink></div></>}
            onReset={() => { setSearch(''); setPage(1); }}
            resetDisabled={!search}
          />
          {type === 'agreements' ? <div className={styles.agreementSwitch} role="group" aria-label="Тип записи"><Button type="button" variant={agreementKind === 'contracts' ? 'primary' : 'ghost'} size="s" data-testid="catalog-agreements-contracts" aria-pressed={agreementKind === 'contracts'} onClick={() => chooseKind('contracts')}>Договоры</Button><Button type="button" variant={agreementKind === 'licenses' ? 'primary' : 'ghost'} size="s" data-testid="catalog-agreements-licenses" aria-pressed={agreementKind === 'licenses'} onClick={() => chooseKind('licenses')}>Лицензии</Button></div> : null}
          <div className={styles.surface}>
            <div className={styles.surfaceHeader}><div><p>{query.data ? `Найдено: ${query.data.total}` : 'Загрузка…'}</p></div></div>
            {query.isPending ? <TableSkeleton rows={5} columns={5} label="Загрузка каталога" />
              : !query.data ? <div className={styles.state}><RouteErrorState compact onRetry={() => void query.refetch()} /></div>
                : query.data.items.length ? <>
                  <CatalogTable type={type} kind={agreementKind} items={query.data.items} canWrite={canWrite} busyId={busyId} universityNames={universityNames} onEdit={setFormItem} onDelete={(item) => { setDeleteError(null); setDeleteTarget(item); }} onContacts={setContactsItem} />
                  <div className={styles.pagination}><span>Страница {page} из {pageCount}</span><Button type="button" variant="ghost" size="s" disabled={page <= 1 || query.isFetching} onClick={() => setPage((value) => value - 1)}>Назад</Button><Button type="button" variant="secondary" size="s" disabled={page >= pageCount || query.isFetching} onClick={() => setPage((value) => value + 1)}>Вперёд</Button></div>
                </> : <div className={styles.state}><EmptyState title="Записи не найдены" description="Измените поисковый запрос или добавьте новую запись." /></div>}
          </div>
        </section>
      </div>
    </TabbedSurface>
    {formItem !== undefined ? <CatalogFormModal type={type} kind={agreementKind} item={formItem} references={references} pending={saveMutation.isPending} onClose={() => { if (!saveMutation.isPending) setFormItem(undefined); }} onSubmit={(input) => saveMutation.mutateAsync({ id: formItem?.id, input }).then(() => undefined)} onError={(error) => setToast({ intent: 'error', title: 'Запись не сохранена', message: error.message })} /> : null}
    {contactsItem ? <Drawer title={`Контакты: ${contactsItem.name}`} onClose={() => setContactsItem(null)}><div className={styles.confirmation}>{contactsQuery.isPending ? <p>Загрузка контактов…</p> : contactsQuery.isError ? <RouteErrorState compact onRetry={() => void contactsQuery.refetch()} /> : <ContactList contacts={itemContacts(contactsQuery.data)} />}</div></Drawer> : null}
    {deleteTarget ? <Modal title="Удалить запись?" onClose={() => { if (!deleteMutation.isPending) setDeleteTarget(null); }}><div className={styles.confirmation}><p><strong>{deleteTarget.name}</strong> будет удалена без возможности восстановления.</p><p>{catalogDeleteBlockers[deleteTarget.type]}</p>{deleteError ? <p className={styles.deleteError} role="alert">{deleteError}</p> : null}<div className={styles.modalActions}><Button type="button" variant="ghost" disabled={deleteMutation.isPending} onClick={() => setDeleteTarget(null)}>Отмена</Button><Button type="button" variant="danger" loading={deleteMutation.isPending} disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate({ item: deleteTarget })}>Удалить</Button></div></div></Modal> : null}
    {toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : null}
  </div>;
}
