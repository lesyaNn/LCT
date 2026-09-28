'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatDateTimeRu } from '@/shared/lib/formatters';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import {
  adminUsersQueryKeys,
  inviteAdminUser,
  getAdminUser,
  listAdminUsers,
  listUserScopeOptions,
  normalizeScopeForRole,
  resetAdminUserPassword,
  scopeDescription,
  scopeLabel,
  setAdminUserBlocked,
  type AdminUser,
  type AdminUserListQuery,
  type AdminUserScope,
  type InviteAdminUserInput,
  updateAdminUser,
  userRoleDescriptions,
  userRoleLabels,
  USERS_API_CAPABILITIES,
} from '@/shared/lib/users-repository';
import type { UserRole } from '@/shared/types/user';
import { Button } from '@/shared/ui/rtk/button';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { EmptyState } from '@/shared/ui/empty-state';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { FilterField, SearchField } from '@/shared/ui/rtk/filter-field';
import { Modal } from '@/shared/ui/rtk/modal';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { TabbedSurface } from '@/shared/ui/rtk/tabbed-surface';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { TableSkeleton } from '@/shared/ui/skeleton';
import styles from './users-page.module.css';

const pageSize = 8;
const roleOptions: Array<{ value: UserRole; label: string }> = [
  { value: 'user', label: userRoleLabels.user },
  { value: 'manager', label: userRoleLabels.manager },
  { value: 'admin', label: userRoleLabels.admin },
];

function statusLabel(status: AdminUser['status']): string {
  return status === 'active' ? 'Активен' : 'Заблокирован';
}

function statusIntent(status: AdminUser['status']): 'success' | 'danger' {
  return status === 'active' ? 'success' : 'danger';
}

function lastLogin(value: string | null): string {
  return value ? formatDateTimeRu(value) : '—';
}

function scopeValues(scope: AdminUserScope): string[] {
  return scope.kind === 'universities' ? scope.universityIds : [];
}

function ScopeEditor({ role, values, options, onChange, disabled = false }: { role: UserRole; values: string[]; options: Array<{ id: string; name: string }>; onChange: (values: string[]) => void; disabled?: boolean }) {
  const adminAll = role === 'admin';
  return <div className={styles.scopeEditor}><div data-testid="scope-multiselect"><MultiSelect label="Доступные ВУЗы" options={options} values={adminAll ? [] : values} onChange={onChange} searchable disabled={disabled || adminAll} placeholder={adminAll ? 'Все ВУЗы' : 'Выберите ВУЗы'} /></div></div>;
}

function RoleSelect({ value, onChange, self }: { value: UserRole; onChange: (value: UserRole) => void; self: boolean }) {
  const control = <Select data-testid="role-select" value={value} disabled={self} onChange={(event) => onChange(event.target.value as UserRole)} aria-describedby={self ? 'self-role-hint' : undefined}>{roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</Select>;
  return self ? <div className={styles.controlTooltip}><Tooltip content="Нельзя снять с себя роль администратора.">{control}</Tooltip></div> : control;
}

function UserRow({ user, options, onOpen }: { user: AdminUser; options: Array<{ id: string; name: string }>; onOpen: (user: AdminUser) => void }) {
  return <tr><td><button className={styles.userButton} type="button" onClick={() => onOpen(user)}>{user.name}<small>{user.username}</small></button></td><td>{user.email}</td><td>{userRoleLabels[user.role]}</td><td><span className={styles.scopeText} title={scopeDescription(user.scope, options)}>{scopeLabel(user.scope)}</span></td><td><StatusBadge intent={statusIntent(user.status)}>{statusLabel(user.status)}</StatusBadge></td><td>{lastLogin(user.lastLoginAt)}</td><td><div className={styles.actions}><Button variant="ghost" size="s" type="button" onClick={() => onOpen(user)}>Настроить</Button></div></td></tr>;
}

function UserCard({ user, onOpen }: { user: AdminUser; onOpen: (user: AdminUser) => void }) {
  return <article className={styles.userCard}><div className={styles.cardTop}><div className={styles.cardName}><strong>{user.name}</strong><span>{user.username} · {user.email}</span></div><StatusBadge intent={statusIntent(user.status)}>{statusLabel(user.status)}</StatusBadge></div><dl className={styles.cardMeta}><div><dt>Роль</dt><dd>{userRoleLabels[user.role]}</dd></div><div><dt>Скоуп</dt><dd>{scopeLabel(user.scope)}</dd></div><div><dt>Последний вход</dt><dd>{lastLogin(user.lastLoginAt)}</dd></div></dl><div className={styles.cardActions}><Button variant="secondary" size="s" type="button" onClick={() => onOpen(user)}>Настроить</Button></div></article>;
}

function IntegrationBlocker({ children }: { children: React.ReactNode }) {
  return <p className={styles.integrationBlocker}>{children}</p>;
}

export function UsersPage() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [role, setRole] = useState<UserRole | 'all'>('all');
  const [page, setPage] = useState(1);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [blockTarget, setBlockTarget] = useState<AdminUser | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [toast, setToast] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);
  const [editorRole, setEditorRole] = useState<UserRole>('user');
  const [editorScope, setEditorScope] = useState<string[]>([]);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [invite, setInvite] = useState<InviteAdminUserInput>({ name: '', username: '', email: '', role: 'user', scope: { kind: 'universities', universityIds: [] } });
  const [inviteError, setInviteError] = useState<string | null>(null);

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedSearch(search), 250); return () => window.clearTimeout(timer); }, [search]);
  const listQuery: AdminUserListQuery = useMemo(() => ({ search: debouncedSearch, role, page, pageSize }), [debouncedSearch, page, role]);
  const query = useQuery({ queryKey: adminUsersQueryKeys.list(listQuery), queryFn: () => listAdminUsers(listQuery), staleTime: 15_000, placeholderData: (previous) => previous });
  const detailQuery = useQuery({ queryKey: adminUsersQueryKeys.detail(selectedUserId ?? ''), queryFn: () => getAdminUser(selectedUserId!), enabled: Boolean(selectedUserId) });
  const scopeOptionsQuery = useQuery({ queryKey: queryKeys.users.scopeOptions, queryFn: listUserScopeOptions, staleTime: 5 * 60_000 });
  const scopeOptions = scopeOptionsQuery.data ?? [];
  const selectedUser = detailQuery.data ?? query.data?.items.find((item) => item.id === selectedUserId) ?? null;
  const isSelf = Boolean(selectedUser && currentUser && selectedUser.id === currentUser.id);
  const pageCount = Math.max(1, Math.ceil((query.data?.total ?? 0) / pageSize));

  const updateMutation = useMutation({
    mutationFn: ({ id, input }: { id: string; input: { role: UserRole; scope: AdminUserScope } }) => updateAdminUser(id, input),
    onError: (cause) => {
      setEditorError(normalizeApiError(cause, { fallbackMessage: 'Не удалось сохранить роль и скоуп.' }).message);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<typeof query.data>(adminUsersQueryKeys.list(listQuery), (current) => current ? { ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) } : current);
      queryClient.setQueryData(adminUsersQueryKeys.detail(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.access });
      void queryClient.invalidateQueries({ queryKey: queryKeys.universities.all });
      setToast({ intent: 'success', title: 'Данные пользователя сохранены' });
    },
  });

  const blockMutation = useMutation({
    mutationFn: ({ id, blocked }: { id: string; blocked: boolean }) => setAdminUserBlocked(id, blocked),
    onError: (cause) => {
      setToast({ intent: 'error', title: 'Не удалось изменить статус', message: normalizeApiError(cause, { fallbackMessage: 'Попробуйте ещё раз.' }).message });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<typeof query.data>(adminUsersQueryKeys.list(listQuery), (current) => current ? { ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) } : current);
      queryClient.setQueryData(adminUsersQueryKeys.detail(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      setBlockTarget(null);
      setToast({ intent: 'success', title: updated.status === 'blocked' ? 'Пользователь заблокирован' : 'Пользователь разблокирован' });
    },
  });

  const resetMutation = useMutation({
    mutationFn: (id: string) => resetAdminUserPassword(id),
    onSuccess: () => { setResetTarget(null); setToast({ intent: 'success', title: 'Письмо для сброса пароля отправлено' }); },
    onError: (cause) => setToast({ intent: 'error', title: 'Сброс пароля недоступен', message: normalizeApiError(cause, { fallbackMessage: 'Попробуйте позже.' }).message }),
  });

  const inviteMutation = useMutation({
    mutationFn: (input: InviteAdminUserInput) => inviteAdminUser(input),
    onSuccess: (result) => {
      setInviteOpen(false);
      setInvite({ name: '', username: '', email: '', role: 'user', scope: { kind: 'universities', universityIds: [] } });
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      setToast({ intent: result.status === 'email_sent' ? 'success' : 'info', title: 'Учётная запись создана', message: result.status === 'email_sent' ? 'Письмо для установки пароля отправлено.' : 'Письмо не отправлено: проверьте настройку почты Keycloak.' });
    },
    onError: (cause) => setInviteError(normalizeApiError(cause, { fallbackMessage: 'Не удалось пригласить пользователя.' }).message),
  });

  const openUser = (item: AdminUser) => { queryClient.setQueryData(adminUsersQueryKeys.detail(item.id), item); setSelectedUserId(item.id); setEditorRole(item.role); setEditorScope(scopeValues(item.scope)); setEditorError(null); };
  const closeUser = () => { if (!updateMutation.isPending && !blockMutation.isPending) setSelectedUserId(null); };
  const changeRole = (nextRole: UserRole) => {
    setEditorRole(nextRole);
    if (nextRole === 'admin') setEditorScope([]);
  };
  const saveUser = () => {
    if (!selectedUser) return;
    if (isSelf && editorRole !== selectedUser.role) { setEditorError('Нельзя снять с себя роль администратора.'); return; }
    updateMutation.mutate({ id: selectedUser.id, input: { role: editorRole, scope: normalizeScopeForRole(editorRole, editorRole === 'admin' ? { kind: 'all' } : { kind: 'universities', universityIds: editorScope }) } });
  };
  const submitInvite = () => {
    if (invite.role !== 'admin' && (scopeOptionsQuery.isPending || scopeOptionsQuery.isError)) { setInviteError('Сначала загрузите каталог ВУЗов.'); return; }
    if (!invite.name.trim() || !invite.username.trim() || !invite.email.trim()) { setInviteError('Заполните ФИО, login и email.'); return; }
    setInviteError(null);
    inviteMutation.mutate({ ...invite, name: invite.name.trim(), username: invite.username.trim(), email: invite.email.trim(), scope: normalizeScopeForRole(invite.role, invite.scope) });
  };

  const renderDrawer = selectedUser ? <Drawer title="Настройки пользователя" onClose={closeUser}><div className={styles.drawerForm}><div className={styles.drawerIntro}><strong>{selectedUser.name}</strong><span>{selectedUser.username} · {selectedUser.email}</span><span>Текущий статус: {statusLabel(selectedUser.status)}</span></div><label className={styles.field}><span>Роль</span><RoleSelect value={editorRole} onChange={changeRole} self={isSelf} />{isSelf ? <small id="self-role-hint" className={styles.muted}>Нельзя снять с себя роль администратора.</small> : null}<small className={styles.roleDescription}>{userRoleDescriptions[editorRole]}</small></label><div className={styles.field}><span>Скоуп данных</span><ScopeEditor role={editorRole} values={editorScope} options={scopeOptions} onChange={setEditorScope} disabled={editorRole === 'admin'} />{editorRole === 'admin' ? <small className={styles.muted}>Доступ ко всем ВУЗам.</small> : <small className={styles.muted}>{scopeDescription({ kind: 'universities', universityIds: editorScope }, scopeOptions)}</small>}{editorRole !== 'admin' && !editorScope.length ? <p className={styles.warning}>Пользователь не увидит ни одного ВУЗа.</p> : null}</div>{detailQuery.isError ? <p className={styles.formError} role="alert">Не удалось обновить данные пользователя.</p> : null}{scopeOptionsQuery.isError ? <p className={styles.formError} role="alert">Не удалось загрузить каталог ВУЗов.</p> : null}{editorError ? <p className={styles.formError} role="alert">{editorError}</p> : null}{!USERS_API_CAPABILITIES.updateRoleAndScope ? <IntegrationBlocker>Изменение роли и области доступа пока недоступно.</IntegrationBlocker> : null}<div className={styles.drawerActions}><Button variant="primary" type="button" loading={updateMutation.isPending} disabled={!USERS_API_CAPABILITIES.updateRoleAndScope || detailQuery.isError || updateMutation.isPending || (editorRole !== 'admin' && (scopeOptionsQuery.isPending || scopeOptionsQuery.isError)) || (isSelf && editorRole !== selectedUser.role)} onClick={saveUser}>Сохранить</Button><Tooltip content={isSelf ? 'Нельзя заблокировать собственную учётную запись.' : !USERS_API_CAPABILITIES.block ? 'Блокировка пока недоступна.' : ''}><Button data-testid="block-button" className={styles.dangerAction} variant="secondary" type="button" disabled={isSelf || detailQuery.isError || !USERS_API_CAPABILITIES.block || blockMutation.isPending} onClick={() => setBlockTarget(selectedUser)}>{selectedUser.status === 'blocked' ? 'Разблокировать' : 'Заблокировать'}</Button></Tooltip><Tooltip content={!USERS_API_CAPABILITIES.passwordReset ? 'Сброс пароля пока недоступен.' : ''}><Button variant="ghost" type="button" disabled={detailQuery.isError || !USERS_API_CAPABILITIES.passwordReset || resetMutation.isPending} onClick={() => setResetTarget(selectedUser)}>Сбросить пароль</Button></Tooltip></div></div></Drawer> : null;

  return <div className={styles.page}><header className={styles.pageHeader}><div><h1>Пользователи и права</h1><p className={styles.description}>Управляйте ролями, статусом и доступом к контуру ВУЗов.</p></div></header><TabbedSurface><div className={styles.panel}><FilterToolbar embedded label="Фильтры пользователей" controls={() => <><SearchField label="Поиск по ФИО, login или email" value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Найти пользователя" /><FilterField label="Роль"><Select value={role} onChange={(event) => { setRole(event.target.value as UserRole | 'all'); setPage(1); }}><option value="all">Все роли</option>{roleOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</Select></FilterField></>} actions={<Button variant="primary" type="button" disabled={!USERS_API_CAPABILITIES.invite} onClick={() => { setInviteError(null); setInviteOpen(true); }}>Добавить пользователя</Button>} onReset={() => { setSearch(''); setRole('all'); setPage(1); }} resetDisabled={!search && role === 'all'} mobileCount={Number(Boolean(search)) + Number(role !== 'all')} activeFilters={[...(search ? [{ id: 'search', label: `Поиск: ${search}`, onRemove: () => { setSearch(''); setPage(1); } }] : []), ...(role !== 'all' ? [{ id: 'role', label: `Роль: ${roleOptions.find((option) => option.value === role)?.label ?? role}`, onRemove: () => { setRole('all'); setPage(1); } }] : [])]} /><section className={styles.surface} data-testid="users-table" aria-labelledby="users-table-heading"><div className={styles.surfaceHeader}><div><h2 id="users-table-heading">Все пользователи</h2><p>{query.data ? `Найдено: ${query.data.total}` : 'Загрузка…'}</p></div></div>{query.isPending ? <TableSkeleton rows={5} columns={7} label="Загрузка пользователей" /> : !query.data ? <div className={styles.empty}><RouteErrorState compact onRetry={() => void query.refetch()} /></div> : query.data?.items.length ? <><TableShell ariaLabel="Пользователи"><div className={styles.desktopTable}><table><thead><tr><th>ФИО / login</th><th>Email</th><th>Роль</th><th>Скоуп</th><th>Статус</th><th>Последний вход</th><th>Действия</th></tr></thead><tbody>{query.data.items.map((item) => <UserRow user={item} options={scopeOptions} onOpen={openUser} key={item.id} />)}</tbody></table></div><div className={styles.mobileList}>{query.data.items.map((item) => <UserCard user={item} onOpen={openUser} key={item.id} />)}</div></TableShell><div className={styles.pagination}><span>Страница {page} из {pageCount}</span><Button variant="ghost" size="s" type="button" disabled={page <= 1 || query.isFetching} onClick={() => setPage((value) => value - 1)}>Назад</Button><Button variant="secondary" size="s" type="button" disabled={page >= pageCount || query.isFetching} onClick={() => setPage((value) => value + 1)}>Вперёд</Button></div></> : <div className={styles.empty}><EmptyState title="Пользователи не найдены" description="Измените поисковый запрос или фильтр роли." /></div>}</section></div></TabbedSurface>{renderDrawer}{inviteOpen ? <Drawer title="Добавить пользователя" onClose={() => { if (!inviteMutation.isPending) setInviteOpen(false); }}><div className={styles.drawerForm}><label className={styles.field}><span>ФИО</span><Input value={invite.name} onChange={(event) => setInvite((current) => ({ ...current, name: event.target.value }))} placeholder="Например, Ольга Соколова" /></label><label className={styles.field}><span>Login</span><Input value={invite.username} onChange={(event) => setInvite((current) => ({ ...current, username: event.target.value }))} placeholder="olga.sokolova" /></label><label className={styles.field}><span>Email</span><Input type="email" value={invite.email} onChange={(event) => setInvite((current) => ({ ...current, email: event.target.value }))} placeholder="olga@example.ru" /></label><label className={styles.field}><span>Роль</span><RoleSelect value={invite.role} onChange={(nextRole) => setInvite((current) => ({ ...current, role: nextRole, scope: normalizeScopeForRole(nextRole, current.scope) }))} self={false} /></label><div className={styles.field}><span>Скоуп данных</span><ScopeEditor role={invite.role} values={scopeValues(invite.scope)} options={scopeOptions} onChange={(values) => setInvite((current) => ({ ...current, scope: { kind: 'universities', universityIds: values } }))} disabled={invite.role === 'admin'} />{invite.role !== 'admin' && !(invite.scope.kind === 'all') && !scopeValues(invite.scope).length ? <p className={styles.warning}>Пользователь не увидит ни одного ВУЗа.</p> : null}</div>{inviteError ? <p className={styles.formError} role="alert">{inviteError}</p> : null}<div className={styles.drawerActions}><Button variant="primary" type="button" loading={inviteMutation.isPending} disabled={inviteMutation.isPending} onClick={submitInvite}>Создать приглашение</Button><Button variant="ghost" type="button" disabled={inviteMutation.isPending} onClick={() => setInviteOpen(false)}>Отмена</Button></div></div></Drawer> : null}{blockTarget ? <Modal title={blockTarget.status === 'blocked' ? 'Разблокировать пользователя?' : 'Заблокировать пользователя?'} onClose={() => { if (!blockMutation.isPending) setBlockTarget(null); }}><div className={styles.modalContent}><p>{blockTarget.name} {blockTarget.status === 'blocked' ? 'снова получит доступ к CRM.' : 'потеряет доступ к CRM.'}</p><div className={styles.modalActions}><Button variant={blockTarget.status === 'blocked' ? 'primary' : 'danger'} type="button" loading={blockMutation.isPending} disabled={blockMutation.isPending} onClick={() => blockMutation.mutate({ id: blockTarget.id, blocked: blockTarget.status !== 'blocked' })}>{blockTarget.status === 'blocked' ? 'Разблокировать' : 'Заблокировать'}</Button><Button variant="ghost" type="button" disabled={blockMutation.isPending} onClick={() => setBlockTarget(null)}>Отмена</Button></div></div></Modal> : null}{resetTarget ? <Modal title="Сбросить пароль пользователя?" onClose={() => { if (!resetMutation.isPending) setResetTarget(null); }}><div className={styles.modalContent}><p>Keycloak отправит пользователю письмо со ссылкой для установки нового пароля.</p><div className={styles.modalActions}><Button variant="primary" type="button" loading={resetMutation.isPending} disabled={resetMutation.isPending} onClick={() => resetMutation.mutate(resetTarget.id)}>Отправить письмо</Button><Button variant="ghost" type="button" disabled={resetMutation.isPending} onClick={() => setResetTarget(null)}>Отмена</Button></div></div></Modal> : null}{toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : null}</div>;
}
