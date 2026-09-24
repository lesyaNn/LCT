'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { normalizeApiError } from '@/shared/lib/api-errors';
import {
  CATALOG_API_CAPABILITIES,
  canMutateCatalog,
  catalogDefinition,
  catalogDefinitions,
  catalogQueryKeys,
  createCatalogItem,
  getCatalogReferenceData,
  listCatalogItems,
  relatedCatalogQueryKeys,
  setCatalogItemActive,
  updateCatalogItem,
  type CatalogInput,
  type CatalogItem,
  type CatalogListQuery,
  type CatalogType,
} from '@/shared/lib/catalogs-repository';
import { Button, ButtonLink } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { Input, Switch } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { TableSkeleton } from '@/shared/ui/skeleton';
import { CatalogFormModal } from './catalog-form-modal';
import styles from './catalogs-page.module.css';

const pageSize = 8;

function secondaryFields(item: CatalogItem): Array<{ label: string; value: string }> {
  if (item.type === 'universities') return [{ label: 'Город', value: item.city || '—' }];
  if (item.type === 'products') return [{ label: 'Вендор', value: item.vendorName || '—' }, { label: 'Версия', value: item.version || '—' }];
  if (item.type === 'directions') return [{ label: 'Код', value: item.code }];
  return [{ label: 'Email', value: item.email }, { label: 'Роль', value: item.role || '—' }, { label: 'ВУЗы', value: item.universityIds.length ? String(item.universityIds.length) : 'Нет' }];
}

function tableHeaders(type: CatalogType): string[] {
  if (type === 'universities') return ['Название', 'Город'];
  if (type === 'products') return ['Название', 'Вендор', 'Версия'];
  if (type === 'directions') return ['Название', 'Код'];
  return ['ФИО', 'Email', 'Роль', 'ВУЗы'];
}

function CatalogActions({ item, canWrite, softActivation, busy, onEdit, onToggle }: { item: CatalogItem; canWrite: boolean; softActivation: boolean; busy: boolean; onEdit: () => void; onToggle: () => void }) {
  const writeHint = canWrite ? null : 'Текущий backend разрешает изменение каталогов только администратору.';
  const activationHint = softActivation ? writeHint : 'Backend не публикует soft activate/deactivate contract; hard delete запрещён.';
  const editButton = <Button type="button" variant="ghost" size="s" disabled={!canWrite || busy} onClick={onEdit}>Изменить</Button>;
  const activationButton = <Button data-testid="deactivate-toggle" type="button" variant="ghost" size="s" disabled={!canWrite || !softActivation || busy} onClick={onToggle}>{item.isActive ? 'Деактивировать' : 'Активировать'}</Button>;
  return <div className={styles.rowActions}>{writeHint ? <Tooltip content={writeHint}>{editButton}</Tooltip> : editButton}{activationHint ? <Tooltip content={activationHint}>{activationButton}</Tooltip> : activationButton}</div>;
}

function CatalogTable({ type, items, canWrite, busyId, onEdit, onToggle }: { type: CatalogType; items: CatalogItem[]; canWrite: boolean; busyId?: string; onEdit: (item: CatalogItem) => void; onToggle: (item: CatalogItem) => void }) {
  const headers = tableHeaders(type);
  return <TableShell ariaLabel={`Каталог «${catalogDefinition(type).label}»`}><div className={styles.desktopTable}><table><caption>Записи каталога</caption><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}<th>Статус</th><th>Действия</th></tr></thead><tbody>{items.map((item) => <tr className={!item.isActive ? styles.inactiveRow : undefined} data-testid={`catalog-row-${item.id}`} key={item.id}><td><button className={styles.nameButton} type="button" disabled={!canWrite} onClick={() => onEdit(item)}>{item.name}</button></td>{secondaryFields(item).map((field) => <td key={field.label}>{field.value}</td>)}<td><StatusBadge intent={item.isActive ? 'success' : 'neutral'}>{item.isActive ? 'Активен' : 'Неактивен'}</StatusBadge></td><td><CatalogActions item={item} canWrite={canWrite} softActivation={CATALOG_API_CAPABILITIES.softActivation} busy={busyId === item.id} onEdit={() => onEdit(item)} onToggle={() => onToggle(item)} /></td></tr>)}</tbody></table></div><div className={styles.mobileList}>{items.map((item) => <article className={`${styles.catalogCard} ${!item.isActive ? styles.inactiveCard : ''}`} key={item.id}><div className={styles.cardTop}><strong>{item.name}</strong><StatusBadge intent={item.isActive ? 'success' : 'neutral'}>{item.isActive ? 'Активен' : 'Неактивен'}</StatusBadge></div><dl>{secondaryFields(item).map((field) => <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl><CatalogActions item={item} canWrite={canWrite} softActivation={CATALOG_API_CAPABILITIES.softActivation} busy={busyId === item.id} onEdit={() => onEdit(item)} onToggle={() => onToggle(item)} /></article>)}</div></TableShell>;
}

export function CatalogsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [type, setType] = useState<CatalogType>('universities');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [page, setPage] = useState(1);
  const [formItem, setFormItem] = useState<CatalogItem | null | undefined>(undefined);
  const [deactivateTarget, setDeactivateTarget] = useState<CatalogItem | null>(null);
  const [toast, setToast] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);
  const canWrite = canMutateCatalog(user?.role);

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedSearch(search), 250); return () => window.clearTimeout(timer); }, [search]);

  const listQuery: CatalogListQuery = useMemo(() => ({ type, search: debouncedSearch, showInactive, page, pageSize }), [debouncedSearch, page, showInactive, type]);
  const query = useQuery({ queryKey: catalogQueryKeys.list(type, listQuery), queryFn: () => listCatalogItems(listQuery), placeholderData: (previous) => previous, staleTime: 15_000 });
  const referencesQuery = useQuery({ queryKey: catalogQueryKeys.references, queryFn: getCatalogReferenceData, staleTime: 60_000 });
  const pageCount = Math.max(1, Math.ceil((query.data?.total ?? 0) / pageSize));

  const invalidateRelated = async (itemType: CatalogType, id?: string) => {
    await Promise.all(relatedCatalogQueryKeys(itemType, id).map((queryKey) => queryClient.invalidateQueries({ queryKey })));
  };

  const saveMutation = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CatalogInput }) => id ? updateCatalogItem(id, input) : createCatalogItem(input),
    onSuccess: async (saved, variables) => {
      await invalidateRelated(saved.type, saved.id);
      setFormItem(undefined);
      setToast({ intent: 'success', title: variables.id ? 'Запись сохранена' : 'Запись добавлена', message: saved.name });
    },
  });

  const activationMutation = useMutation({
    mutationFn: ({ item, active }: { item: CatalogItem; active: boolean }) => setCatalogItemActive(item.type, item.id, active),
    onSuccess: async (saved) => {
      await invalidateRelated(saved.type, saved.id);
      setDeactivateTarget(null);
      setToast({ intent: 'success', title: saved.isActive ? 'Запись активирована' : 'Запись деактивирована', message: saved.name });
    },
    onError: (cause) => setToast({ intent: 'error', title: 'Статус не изменён', message: normalizeApiError(cause, { fallbackMessage: 'Попробуйте ещё раз.' }).message }),
  });

  const chooseType = (next: CatalogType) => { setType(next); setSearch(''); setDebouncedSearch(''); setShowInactive(false); setPage(1); setFormItem(undefined); setDeactivateTarget(null); };
  const toggle = (item: CatalogItem) => { if (item.isActive) setDeactivateTarget(item); else activationMutation.mutate({ item, active: true }); };
  const definition = catalogDefinition(type);
  const references = referencesQuery.data ?? { vendors: [], universities: [] };
  const referencesRequired = type === 'products' || type === 'responsibles';
  const formReferencesReady = !referencesRequired || (!referencesQuery.isPending && !referencesQuery.isError);
  const integrationNotes = [
    !CATALOG_API_CAPABILITIES.softActivation ? 'Soft activate/deactivate отсутствует в текущем backend; hard DELETE намеренно не используется.' : null,
    !canWrite ? 'Для вашей роли каталог доступен только для чтения согласно backend permissions.' : null,
  ].filter(Boolean);
  const addButton = <Button data-testid="catalog-add" type="button" variant="primary" disabled={!canWrite || !formReferencesReady} onClick={() => setFormItem(null)}>Добавить</Button>;

  return <div className={styles.page}><nav className={styles.localBreadcrumbs} aria-label="Хлебные крошки"><Link href="/admin">Администрирование</Link><span aria-hidden="true">/</span><span aria-current="page">Управление каталогами</span></nav><header className={styles.pageHeader}><div><p className={styles.eyebrow}>Администрирование</p><h1>Управление каталогами</h1><p>Единый CRUD-интерфейс для основных справочников CRM.</p></div></header><div className={styles.tabScroller} data-testid="catalog-tabs"><div className={styles.tabs} role="tablist" aria-label="Каталоги">{catalogDefinitions.map((tab) => <button className={type === tab.id ? styles.tabActive : styles.tab} id={`catalog-tab-${tab.id}`} role="tab" aria-selected={type === tab.id} aria-controls="catalog-panel" type="button" onClick={() => chooseType(tab.id)} key={tab.id}>{tab.label}</button>)}</div></div><section id="catalog-panel" role="tabpanel" aria-labelledby={`catalog-tab-${type}`} className={styles.panel}><div className={styles.toolbar}><label className={styles.search}><span>Поиск</span><Input type="search" value={search} placeholder={definition.searchPlaceholder} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label><div className={styles.inactiveFilter}><Switch checked={showInactive} disabled={!CATALOG_API_CAPABILITIES.inactiveFilter} label="Показывать неактивные" onChange={(value) => { setShowInactive(value); setPage(1); }} /><span>Показывать неактивные</span></div><div className={styles.actions}>{canWrite ? addButton : <Tooltip content="Текущий backend разрешает изменение каталогов только администратору.">{addButton}</Tooltip>}<ButtonLink href={`/admin/import?type=${type}`} variant="secondary">Импорт</ButtonLink></div></div>{integrationNotes.length ? <div className={styles.integrationNote}>{integrationNotes.map((note) => <p key={note}>{note}</p>)}</div> : null}<div className={styles.surface}><div className={styles.surfaceHeader}><div><h2>{definition.label}</h2><p>{query.data ? `Найдено: ${query.data.total}` : 'Загрузка…'}</p></div></div>{query.isPending ? <TableSkeleton rows={5} columns={5} label="Загрузка каталога" /> : query.isError ? <div className={styles.state}><RouteErrorState compact onRetry={() => void query.refetch()} /></div> : query.data?.items.length ? <><CatalogTable type={type} items={query.data.items} canWrite={canWrite} busyId={activationMutation.isPending ? activationMutation.variables?.item.id : undefined} onEdit={(item) => setFormItem(item)} onToggle={toggle} /><div className={styles.pagination}><span>Страница {page} из {pageCount}</span><Button type="button" variant="ghost" size="s" disabled={page <= 1 || query.isFetching} onClick={() => setPage((value) => value - 1)}>Назад</Button><Button type="button" variant="secondary" size="s" disabled={page >= pageCount || query.isFetching} onClick={() => setPage((value) => value + 1)}>Вперёд</Button></div></> : <div className={styles.state}><EmptyState title="Записи не найдены" description="Измените поисковый запрос или фильтр неактивных записей." /></div>}</div></section>{formItem !== undefined ? <CatalogFormModal type={type} item={formItem} references={references} pending={saveMutation.isPending} onClose={() => { if (!saveMutation.isPending) setFormItem(undefined); }} onSubmit={(input) => saveMutation.mutateAsync({ id: formItem?.id, input }).then(() => undefined)} onError={(error) => setToast({ intent: 'error', title: 'Запись не сохранена', message: error.message })} /> : null}{deactivateTarget ? <Modal title="Деактивировать запись?" onClose={() => { if (!activationMutation.isPending) setDeactivateTarget(null); }}><div className={styles.confirmation}><p><strong>{deactivateTarget.name}</strong> станет недоступна в активных списках, но останется в каталоге.</p><p>Связанные данные не удаляются.</p><div className={styles.modalActions}><Button type="button" variant="ghost" disabled={activationMutation.isPending} onClick={() => setDeactivateTarget(null)}>Отмена</Button><Button type="button" variant="danger" loading={activationMutation.isPending} disabled={activationMutation.isPending} onClick={() => activationMutation.mutate({ item: deactivateTarget, active: false })}>Деактивировать</Button></div></div></Modal> : null}{toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : null}</div>;
}
