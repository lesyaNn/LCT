'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { networkGraphQueryKey } from '@/shared/lib/network-repository';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { emailField } from '@/shared/lib/form-validation';
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
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { EmptyState } from '@/shared/ui/empty-state';
import { Input, Select, Switch } from '@/shared/ui/rtk/form-controls';
import { Icon } from '@/shared/ui/rtk/icon';
import Lock from '@atomaro/icons/24/action/Lock';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { FilterField, SearchField } from '@/shared/ui/rtk/filter-field';
import { Modal } from '@/shared/ui/rtk/modal';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import tableStyles from '@/shared/ui/rtk/data-table.module.css';
import { TabbedSurface } from '@/shared/ui/rtk/tabbed-surface';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { TableSkeleton } from '@/shared/ui/skeleton';
import { NetworkGraph } from '@/widgets/network/network-graph';
import styles from './users-page.module.css';

const pageSize = 8;
type UsersView = 'table' | 'graph';
type InviteField = 'name' | 'username' | 'email';
const viewTabs = [{ id: 'table', label: 'Список' }, { id: 'graph', label: 'Граф связей' }] as const;
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

function UserRow({ user, options, onOpen, showRole }: { user: AdminUser; options: Array<{ id: string; name: string }>; onOpen: (user: AdminUser) => void; showRole: boolean }) {
  return <tr><td><button className={styles.userButton} type="button" onClick={() => onOpen(user)}>{user.name}<small>{user.username}</small></button></td><td>{user.email}</td>{showRole ? <td>{userRoleLabels[user.role]}</td> : null}<td><span className={styles.scopeText} title={scopeDescription(user.scope, options)}>{scopeLabel(user.scope)}</span></td><td><StatusBadge intent={statusIntent(user.status)}>{statusLabel(user.status)}</StatusBadge></td><td><div className={styles.actions}><Button variant="ghost" size="s" type="button" onClick={() => onOpen(user)}>{showRole ? 'Настроить' : 'Назначить вузы'}</Button></div></td></tr>;
}

function UserCard({ user, onOpen, showRole }: { user: AdminUser; onOpen: (user: AdminUser) => void; showRole: boolean }) {
  return <article className={styles.userCard}><div className={styles.cardTop}><div className={styles.cardName}><strong>{user.name}</strong><span>{user.username} · {user.email}</span></div><StatusBadge intent={statusIntent(user.status)}>{statusLabel(user.status)}</StatusBadge></div><dl className={styles.cardMeta}>{showRole ? <div><dt>Роль</dt><dd>{userRoleLabels[user.role]}</dd></div> : null}<div><dt>{showRole ? 'Скоуп' : 'Вузы'}</dt><dd>{scopeLabel(user.scope)}</dd></div></dl><div className={styles.cardActions}><Button variant="secondary" size="s" type="button" onClick={() => onOpen(user)}>{showRole ? 'Настроить' : 'Назначить вузы'}</Button></div></article>;
}

function IntegrationBlocker({ children }: { children: React.ReactNode }) {
  return <p className={styles.integrationBlocker}>{children}</p>;
}

export function UsersPage() {
  const { user: currentUser } = useAuth();
  const canManageUsers = hasPermission(currentUser, 'admin.users');
  const viewerKey = `${currentUser?.id ?? 'anonymous'}:${canManageUsers ? 'admin' : 'assignments'}`;
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [role, setRole] = useState<UserRole | 'all'>('all');
  const [page, setPage] = useState(1);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [view, setView] = useState<UsersView>('table');
  const [inviteOpen, setInviteOpen] = useState(false);
  const [blockTarget, setBlockTarget] = useState<AdminUser | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);
  const [editorRole, setEditorRole] = useState<UserRole>('user');
  const [editorScope, setEditorScope] = useState<string[]>([]);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [invite, setInvite] = useState<InviteAdminUserInput>({ name: '', username: '', email: '', role: 'user', scope: { kind: 'universities', universityIds: [] } });
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteFieldErrors, setInviteFieldErrors] = useState<Partial<Record<InviteField, string>>>({});
  const updateSubmitting = useRef(false);
  const blockSubmitting = useRef(false);
  const resetSubmitting = useRef(false);
  const inviteSubmitting = useRef(false);

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedSearch(search), 250); return () => window.clearTimeout(timer); }, [search]);
  const listQuery: AdminUserListQuery = useMemo(() => ({ search: debouncedSearch, role: canManageUsers ? role : 'user', page, pageSize }), [canManageUsers, debouncedSearch, page, role]);
  const listKey = [...adminUsersQueryKeys.list(listQuery), viewerKey] as const;
  const detailKey = (id: string) => [...adminUsersQueryKeys.detail(id), viewerKey] as const;
  const query = useQuery({ queryKey: listKey, queryFn: () => listAdminUsers(listQuery), staleTime: 15_000, placeholderData: canManageUsers ? (previous) => previous : undefined });
  const detailQuery = useQuery({ queryKey: detailKey(selectedUserId ?? ''), queryFn: () => getAdminUser(selectedUserId!), enabled: Boolean(selectedUserId) });
  const scopeOptionsQuery = useQuery({ queryKey: queryKeys.users.scopeOptions, queryFn: listUserScopeOptions, staleTime: 5 * 60_000 });
  const scopeOptions = canManageUsers ? (scopeOptionsQuery.data ?? []) : (scopeOptionsQuery.data ?? []).filter((option) => currentUser?.scope.universityIds.includes(option.id));
  const selectedUser = detailQuery.data ?? query.data?.items.find((item) => item.id === selectedUserId) ?? null;
  const selectedUserInitials = selectedUser?.name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('ru-RU') || '—';
  const isSelf = Boolean(selectedUser && currentUser && selectedUser.id === currentUser.id);
  const pageCount = Math.max(1, Math.ceil((query.data?.total ?? 0) / pageSize));

  const updateMutation = useMutation({
    mutationFn: ({ id, input }: { id: string; input: { role: UserRole; scope: AdminUserScope } }) => updateAdminUser(id, input),
    onError: (cause) => {
      setEditorError(normalizeApiError(cause, { fallbackMessage: 'Не удалось сохранить назначение вузов.' }).message);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<typeof query.data>(listKey, (current) => current ? { ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) } : current);
      queryClient.setQueryData(detailKey(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.access });
      void queryClient.invalidateQueries({ queryKey: networkGraphQueryKey });
      void queryClient.invalidateQueries({ queryKey: queryKeys.universities.all });
      setToast({ intent: 'success', title: canManageUsers ? 'Данные пользователя сохранены' : 'Назначения вузов сохранены' });
      if (!canManageUsers) setSelectedUserId(null);
    },
    onSettled: () => { updateSubmitting.current = false; },
  });

  const blockMutation = useMutation({
    mutationFn: ({ id, blocked }: { id: string; blocked: boolean }) => setAdminUserBlocked(id, blocked),
    onError: (cause) => {
      setToast({ intent: 'error', title: 'Не удалось изменить статус', message: normalizeApiError(cause, { fallbackMessage: 'Попробуйте ещё раз.' }).message });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<typeof query.data>(listKey, (current) => current ? { ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) } : current);
      queryClient.setQueryData(detailKey(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      setBlockTarget(null);
      setToast({ intent: 'success', title: updated.status === 'blocked' ? 'Пользователь заблокирован' : 'Пользователь разблокирован' });
    },
    onSettled: () => { blockSubmitting.current = false; },
  });

  const resetMutation = useMutation({
    mutationFn: (id: string) => resetAdminUserPassword(id),
    onSuccess: () => { setResetTarget(null); setToast({ intent: 'success', title: 'Письмо для сброса пароля отправлено' }); },
    onError: (cause) => setResetError(normalizeApiError(cause, { fallbackMessage: 'Keycloak не отправил письмо. Повторите попытку позже.' }).message),
    onSettled: () => { resetSubmitting.current = false; },
  });

  const inviteMutation = useMutation({
    mutationFn: (input: InviteAdminUserInput) => inviteAdminUser(input),
    onSuccess: (result) => {
      setInviteOpen(false);
      setInvite({ name: '', username: '', email: '', role: 'user', scope: { kind: 'universities', universityIds: [] } });
      setInviteFieldErrors({});
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      setToast({ intent: result.status === 'email_sent' ? 'success' : 'info', title: 'Учётная запись создана', message: result.status === 'email_sent' ? 'Письмо для установки пароля отправлено.' : 'Письмо не отправлено: проверьте настройку почты Keycloak.' });
    },
    onError: (cause) => {
      const error = normalizeApiError(cause, { fallbackMessage: 'Не удалось пригласить пользователя.' });
      setInviteFieldErrors(Object.fromEntries(error.fieldErrors.filter((field) => ['name', 'username', 'email'].includes(field.field)).map((field) => [field.field, field.message])));
      setInviteError(error.status === 409 ? 'Пользователь с таким email или login уже существует.' : error.status === 403 ? 'Недостаточно прав для приглашения пользователя.' : error.fieldErrors.some((field) => field.field.startsWith('scope.')) ? 'Проверьте выбранные ВУЗы.' : error.message);
    },
    onSettled: () => { inviteSubmitting.current = false; },
  });

  const openUser = (item: AdminUser) => { queryClient.setQueryData(detailKey(item.id), item); setSelectedUserId(item.id); setEditorRole(item.role); setEditorScope(scopeValues(item.scope)); setEditorError(null); };
  const closeUser = () => { if (!updateMutation.isPending && !blockMutation.isPending) setSelectedUserId(null); };
  const changeRole = (nextRole: UserRole) => {
    setEditorRole(nextRole);
    if (nextRole === 'admin') setEditorScope([]);
  };
  const saveUser = () => {
    if (!selectedUser || updateSubmitting.current || updateMutation.isPending) return;
    if (!canManageUsers && editorRole !== selectedUser.role) { setEditorError('Изменение роли недоступно.'); return; }
    if (isSelf && editorRole !== selectedUser.role) { setEditorError('Нельзя снять с себя роль администратора.'); return; }
    updateSubmitting.current = true;
    updateMutation.mutate({ id: selectedUser.id, input: { role: editorRole, scope: normalizeScopeForRole(editorRole, editorRole === 'admin' ? { kind: 'all' } : { kind: 'universities', universityIds: editorScope }) } });
  };
  const submitInvite = () => {
    if (inviteSubmitting.current || inviteMutation.isPending) return;
    const name = invite.name.trim();
    const username = invite.username.trim();
    const emailResult = emailField(256).safeParse(invite.email);
    const fieldErrors: Partial<Record<InviteField, string>> = {};
    if (name.length < 2 || name.length > 256) fieldErrors.name = 'Укажите ФИО от 2 до 256 символов.';
    if (username.length < 2 || username.length > 128 || !/^[A-Za-z0-9._@-]+$/.test(username)) fieldErrors.username = 'Login: 2–128 символов, латиница, цифры, точка, _, @ или -.';
    if (!emailResult.success) fieldErrors.email = emailResult.error.issues[0]?.message ?? 'Введите корректный email.';
    setInviteFieldErrors(fieldErrors);
    if (Object.keys(fieldErrors).length || !emailResult.success) { setInviteError('Исправьте ошибки в форме.'); return; }
    setInviteError(null);
    inviteSubmitting.current = true;
    inviteMutation.mutate({ ...invite, name, username, email: emailResult.data, scope: normalizeScopeForRole(invite.role, invite.scope) });
  };

  const renderDrawer = selectedUser ? (
    <Drawer title={canManageUsers ? 'Настройки пользователя' : 'Назначение вузов'} className={styles.settingsDrawer} onClose={closeUser} footer={<div className={styles.userSettingsActions}>
      {canManageUsers ? <Button className={styles.resetPasswordButton} variant="secondary" size="s" type="button" disabled={detailQuery.isError || !USERS_API_CAPABILITIES.passwordReset || resetMutation.isPending} onClick={() => { setResetError(null); setResetTarget(selectedUser); }}><Lock size={16} fill="currentColor" />Сбросить пароль</Button> : null}
      <div className={styles.userSettingsActionGroup}><Button variant="ghost" size="s" type="button" disabled={updateMutation.isPending || blockMutation.isPending} onClick={closeUser}>Отмена</Button><Button variant="primary" size="s" type="button" loading={updateMutation.isPending} disabled={!USERS_API_CAPABILITIES.updateRoleAndScope || detailQuery.isError || updateMutation.isPending || (editorRole !== 'admin' && (scopeOptionsQuery.isPending || scopeOptionsQuery.isError)) || (isSelf && editorRole !== selectedUser.role)} onClick={saveUser}>Сохранить</Button></div>
    </div>}>
      <div className={styles.drawerForm}>
        <div className={styles.drawerIntro}>
          <Avatar initials={selectedUserInitials} size="l" />
          <div className={styles.drawerIdentity}>
            <strong>{selectedUser.name}</strong>
            <span>{selectedUser.username} · {selectedUser.email}</span>
            <StatusBadge intent={statusIntent(selectedUser.status)}>{statusLabel(selectedUser.status)}</StatusBadge>
          </div>
        </div>
        {canManageUsers ? (
          <div className={styles.field}>
            <span>Роль</span>
            <div className={styles.roleSelectRow}><span className={styles.roleIcon} aria-hidden="true"><Icon name={editorRole === 'admin' ? 'audit' : editorRole === 'manager' ? 'admin' : 'user'} size={20} /></span><RoleSelect value={editorRole} onChange={changeRole} self={isSelf} /></div>
            {isSelf ? <small id="self-role-hint" className={styles.muted}>Нельзя снять с себя роль администратора.</small> : null}
            <small className={styles.roleDescription}><InformationStroke size={18} fill="currentColor" aria-hidden="true" />{userRoleDescriptions[editorRole]}</small>
          </div>
        ) : null}
        <div className={styles.field}>
          <span>{canManageUsers ? 'Скоуп данных' : 'Доступные ВУЗы'}</span>
          <ScopeEditor role={editorRole} values={editorScope} options={scopeOptions} onChange={setEditorScope} disabled={editorRole === 'admin'} />
          {editorRole === 'admin'
            ? <small className={styles.muted}>Доступ ко всем ВУЗам.</small>
            : <small className={styles.muted}>{!canManageUsers && !editorScope.length ? 'Нет назначений в вашем контуре.' : scopeDescription({ kind: 'universities', universityIds: editorScope }, scopeOptions)}</small>}
          {canManageUsers && editorRole !== 'admin' && !editorScope.length ? <p className={styles.warning}>Пользователь не увидит ни одного ВУЗа.</p> : null}
        </div>
        {canManageUsers ? <div className={styles.statusField}><span>Статус</span><div><Switch checked={selectedUser.status === 'active'} onChange={(active) => { if (active !== (selectedUser.status === 'active')) setBlockTarget(selectedUser); }} label="Активен" testId="block-button" disabled={isSelf || detailQuery.isError || !USERS_API_CAPABILITIES.block || blockMutation.isPending || updateMutation.isPending} /><strong>{statusLabel(selectedUser.status)}</strong></div><small>{selectedUser.status === 'active' ? 'При отключении пользователь потеряет доступ к CRM.' : 'При включении пользователь снова получит доступ к CRM.'}</small>{isSelf ? <small className={styles.muted}>Свою учётную запись отключить нельзя.</small> : null}</div> : null}
        {detailQuery.isError ? <p className={styles.formError} role="alert">Не удалось обновить данные пользователя.</p> : null}
        {scopeOptionsQuery.isError ? <p className={styles.formError} role="alert">Не удалось загрузить каталог ВУЗов.</p> : null}
        {editorError ? <p className={styles.formError} role="alert">{editorError}</p> : null}
        {!USERS_API_CAPABILITIES.updateRoleAndScope ? <IntegrationBlocker>{canManageUsers ? 'Изменение роли и области доступа пока недоступно.' : 'Назначение вузов пока недоступно.'}</IntegrationBlocker> : null}
      </div>
    </Drawer>
  ) : null;

  return <div className={styles.page}><header className={styles.pageHeader}><div><h1>{canManageUsers ? 'Пользователи и права' : 'Пользователи и вузы'}</h1>{canManageUsers ? <p className={styles.description}>Управляйте ролями, статусом и доступом к контуру ВУЗов.</p> : null}</div></header><TabbedSurface><div className={styles.panel}><Tabs items={viewTabs} activeId={view} onChange={(id) => setView(id === 'graph' ? 'graph' : 'table')} label="Представление страницы" />{view === 'table' ? <><FilterToolbar embedded label="Фильтры пользователей" controls={() => <><SearchField label="Поиск по ФИО, login или email" value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Найти пользователя" />{canManageUsers ? <FilterField label="Роль"><Select value={role} onChange={(event) => { setRole(event.target.value as UserRole | 'all'); setPage(1); }}><option value="all">Все роли</option>{roleOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</Select></FilterField> : null}</>} actions={canManageUsers ? <Button variant="primary" type="button" disabled={!USERS_API_CAPABILITIES.invite} onClick={() => { setInviteError(null); setInviteFieldErrors({}); setInviteOpen(true); }}>Создать приглашение</Button> : undefined} onReset={() => { setSearch(''); setRole('all'); setPage(1); }} resetDisabled={!search && role === 'all'} mobileCount={Number(Boolean(search)) + Number(canManageUsers && role !== 'all')} activeFilters={[...(search ? [{ id: 'search', label: `Поиск: ${search}`, onRemove: () => { setSearch(''); setPage(1); } }] : []), ...(canManageUsers && role !== 'all' ? [{ id: 'role', label: `Роль: ${roleOptions.find((option) => option.value === role)?.label ?? role}`, onRemove: () => { setRole('all'); setPage(1); } }] : [])]} /><section className={styles.surface} data-testid="users-table" aria-labelledby="users-table-heading"><div className={styles.surfaceHeader}><div><h2 id="users-table-heading">Все пользователи</h2><p>{query.data ? `Найдено: ${query.data.total}` : 'Загрузка…'}</p></div></div>{query.isPending ? <TableSkeleton rows={5} columns={canManageUsers ? 6 : 5} label="Загрузка пользователей" /> : !query.data ? <div className={styles.empty}><RouteErrorState compact onRetry={() => void query.refetch()} /></div> : query.data?.items.length ? <><TableShell ariaLabel="Пользователи"><div className={styles.desktopTable}><table className={tableStyles.table}><thead><tr><th>ФИО / login</th><th>Email</th>{canManageUsers ? <th>Роль</th> : null}<th>{canManageUsers ? 'Скоуп' : 'Вузы'}</th><th>Статус</th><th>Действия</th></tr></thead><tbody>{query.data.items.map((item) => <UserRow user={item} options={scopeOptions} onOpen={openUser} showRole={canManageUsers} key={item.id} />)}</tbody></table></div><div className={styles.mobileList}>{query.data.items.map((item) => <UserCard user={item} onOpen={openUser} showRole={canManageUsers} key={item.id} />)}</div></TableShell><div className={styles.pagination}><span>Страница {page} из {pageCount}</span><Button variant="ghost" size="s" type="button" disabled={page <= 1 || query.isFetching} onClick={() => setPage((value) => value - 1)}>Назад</Button><Button variant="secondary" size="s" type="button" disabled={page >= pageCount || query.isFetching} onClick={() => setPage((value) => value + 1)}>Вперёд</Button></div></> : <div className={styles.empty}><EmptyState title="Пользователи не найдены" description={canManageUsers ? 'Измените поисковый запрос или фильтр роли.' : 'Измените поисковый запрос.'} /></div>}</section></> : <section className={styles.surface} aria-labelledby="users-graph-heading"><div className={styles.surfaceHeader}><div><h2 id="users-graph-heading">Граф связей</h2><p>{canManageUsers ? 'Сотрудники и вузы, которые они ведут. Нажмите на узел, чтобы увидеть детали и назначить вуз.' : 'Доступные вам сотрудники и вузы. Нажмите на узел, чтобы увидеть связи.'}</p></div></div><NetworkGraph showIntro={false} /></section>}</div></TabbedSurface>{renderDrawer}{canManageUsers && inviteOpen ? (
    <Drawer title="Создать приглашение" onClose={() => { if (!inviteMutation.isPending) setInviteOpen(false); }}>
      <form className={styles.drawerForm} onSubmit={(event) => { event.preventDefault(); submitInvite(); }} noValidate>
        <label className={styles.field}>
          <span>ФИО</span>
          <Input value={invite.name} aria-invalid={Boolean(inviteFieldErrors.name)} onChange={(event) => { setInvite((current) => ({ ...current, name: event.target.value })); setInviteFieldErrors((current) => ({ ...current, name: undefined })); setInviteError(null); }} placeholder="Например, Ольга Соколова" />
          {inviteFieldErrors.name ? <small className={styles.formError} role="alert">{inviteFieldErrors.name}</small> : null}
        </label>
        <label className={styles.field}>
          <span>Login</span>
          <Input value={invite.username} aria-invalid={Boolean(inviteFieldErrors.username)} onChange={(event) => { setInvite((current) => ({ ...current, username: event.target.value })); setInviteFieldErrors((current) => ({ ...current, username: undefined })); setInviteError(null); }} placeholder="olga.sokolova" />
          {inviteFieldErrors.username ? <small className={styles.formError} role="alert">{inviteFieldErrors.username}</small> : null}
        </label>
        <label className={styles.field}>
          <span>Email</span>
          <Input type="email" value={invite.email} aria-invalid={Boolean(inviteFieldErrors.email)} onChange={(event) => { setInvite((current) => ({ ...current, email: event.target.value })); setInviteFieldErrors((current) => ({ ...current, email: undefined })); setInviteError(null); }} placeholder="olga@example.ru" />
          {inviteFieldErrors.email ? <small className={styles.formError} role="alert">{inviteFieldErrors.email}</small> : null}
        </label>
        <label className={styles.field}>
          <span>Роль</span>
          <RoleSelect value={invite.role} onChange={(nextRole) => setInvite((current) => ({ ...current, role: nextRole, scope: normalizeScopeForRole(nextRole, current.scope) }))} self={false} />
        </label>
        <div className={styles.field}>
          <span>Скоуп данных</span>
          <ScopeEditor role={invite.role} values={scopeValues(invite.scope)} options={scopeOptions} onChange={(values) => setInvite((current) => ({ ...current, scope: { kind: 'universities', universityIds: values } }))} disabled={invite.role === 'admin'} />
          {invite.role !== 'admin' && scopeOptionsQuery.isError ? <small className={styles.formError} role="alert">Не удалось загрузить список ВУЗов. Приглашение можно создать без назначений.</small> : null}
          {invite.role !== 'admin' && invite.scope.kind !== 'all' && !scopeValues(invite.scope).length ? <p className={styles.warning}>Пользователь не увидит ни одного ВУЗа.</p> : null}
        </div>
        {inviteError ? <p className={styles.formError} role="alert">{inviteError}</p> : null}
        <div className={styles.drawerActions}>
          <Button variant="primary" type="submit" loading={inviteMutation.isPending} disabled={inviteMutation.isPending}>Создать приглашение</Button>
          <Button variant="ghost" type="button" disabled={inviteMutation.isPending} onClick={() => setInviteOpen(false)}>Отмена</Button>
        </div>
      </form>
    </Drawer>
  ) : null}
  {canManageUsers && blockTarget ? <Modal title={blockTarget.status === 'blocked' ? 'Разблокировать пользователя?' : 'Заблокировать пользователя?'} onClose={() => { if (!blockMutation.isPending) setBlockTarget(null); }}><div className={styles.modalContent}><p>{blockTarget.name} {blockTarget.status === 'blocked' ? 'снова получит доступ к CRM.' : 'потеряет доступ к CRM.'}</p><div className={styles.modalActions}><Button variant={blockTarget.status === 'blocked' ? 'primary' : 'danger'} type="button" loading={blockMutation.isPending} disabled={blockMutation.isPending} onClick={() => { if (blockSubmitting.current) return; blockSubmitting.current = true; blockMutation.mutate({ id: blockTarget.id, blocked: blockTarget.status !== 'blocked' }); }}>{blockTarget.status === 'blocked' ? 'Разблокировать' : 'Заблокировать'}</Button><Button variant="ghost" type="button" disabled={blockMutation.isPending} onClick={() => setBlockTarget(null)}>Отмена</Button></div></div></Modal> : null}{canManageUsers && resetTarget ? <Modal title="Сбросить пароль пользователя?" onClose={() => { if (!resetMutation.isPending) setResetTarget(null); }}><div className={styles.modalContent}><p>Keycloak отправит пользователю письмо со ссылкой для установки нового пароля.</p>{resetError ? <p className={styles.formError} role="alert">{resetError}</p> : null}<div className={styles.modalActions}><Button variant="primary" type="button" loading={resetMutation.isPending} disabled={resetMutation.isPending} onClick={() => { if (resetSubmitting.current) return; resetSubmitting.current = true; resetMutation.mutate(resetTarget.id); }}>Отправить письмо</Button><Button variant="ghost" type="button" disabled={resetMutation.isPending} onClick={() => setResetTarget(null)}>Отмена</Button></div></div></Modal> : null}{toast ? <div className={styles.toastViewport}><Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /></div> : null}</div>;
}
