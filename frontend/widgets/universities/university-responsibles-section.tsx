'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Mail from '@atomaro/icons/24/communication/Mail';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { removeUniversityResponsible } from '@/shared/lib/users-repository';
import { getUniversityResponsibles, universityResponsiblesQueryKey, type UniversityResponsibleContact } from '@/shared/lib/universities-repository';
import { EmptyState } from '@/shared/ui/empty-state';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Button } from '@/shared/ui/rtk/button';
import { Modal } from '@/shared/ui/rtk/modal';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { Toast } from '@/shared/ui/rtk/toast';
import { PassportTableSkeleton } from './passport-data-table';
import { ResponsibleAssignmentDrawer } from './responsible-assignment-drawer';
import { ResponsibleCard } from './responsible-card';
import { invalidateResponsibleQueries } from './responsible-queries';
import styles from './university-responsibles-section.module.css';

export function ResponsiblesSection({ id, canEdit }: { id: string; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canManage = hasPermission(user, 'university_responsible.manage') && !isMockDataSourceFor('passport');
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<UniversityResponsibleContact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState(false);
  const query = useQuery({ queryKey: universityResponsiblesQueryKey(id), queryFn: () => getUniversityResponsibles(id, queryClient), staleTime: 30_000 });
  const remove = useMutation({
    mutationFn: (responsibleId: string) => removeUniversityResponsible(id, responsibleId),
    onSuccess: async () => { await invalidateResponsibleQueries(queryClient, id); setRemoveTarget(null); setToast(true); },
    onError: (cause) => setError(normalizeApiError(cause, { fallbackMessage: 'Не удалось снять ответственного.' }).message),
  });

  if (query.isPending) return <section className={styles.section} aria-label="Ответственные"><PassportTableSkeleton /></section>;
  if (!query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;
  const currentPrimary = query.data.find((person) => person.isPrimary);

  return <>
    <section className={styles.section} aria-labelledby="passport-responsibles-title">
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitle}><h2 id="passport-responsibles-title">Ответственные</h2><StatusBadge intent="neutral" showIndicator={false}>{query.data.length}</StatusBadge></div>
        {canManage || canEdit ? <div className={styles.toolbar}><Button variant="primary" size="s" type="button" onClick={() => setAssignmentOpen(true)}>Добавить ответственного</Button></div> : null}
      </div>
      {query.data.length ? <div className={styles.grid}>{query.data.map((person) => <ResponsibleCard key={person.id} person={person} onRemove={canManage ? () => { setError(null); setRemoveTarget(person); } : undefined} />)}</div> : <EmptyState icon={<Mail size={20} fill="currentColor" />} title="Ответственные не назначены" description="Контактные лица появятся здесь после назначения." headingLevel={3} />}
    </section>
    {assignmentOpen ? <ResponsibleAssignmentDrawer id={id} primaryId={currentPrimary?.id ?? ''} existingIds={query.data.map((person) => person.id)} allowAdd={canManage} allowPrimary={canEdit} onClose={() => setAssignmentOpen(false)} onSuccess={() => { setAssignmentOpen(false); setToast(true); }} /> : null}
    {removeTarget ? <Modal title="Вы точно хотите снять ответственного?" onClose={() => { if (!remove.isPending) setRemoveTarget(null); }}>
      <p>«{removeTarget.name}» будет снят с назначения в этом ВУЗе.{removeTarget.isPrimary ? ' Основного ответственного после этого нужно будет назначить заново.' : ''}</p>
      {error ? <p className={styles.assignmentError} role="alert">{error}</p> : null}
      <div className={styles.actions}><Button variant="ghost" type="button" disabled={remove.isPending} onClick={() => setRemoveTarget(null)}>Отмена</Button><Button variant="danger" type="button" loading={remove.isPending} disabled={remove.isPending} onClick={() => remove.mutate(removeTarget.id)}>Снять назначение</Button></div>
    </Modal> : null}
    {toast ? <Toast intent="success" title="Назначения обновлены" message="Паспорт и связанные списки обновляются." onClose={() => setToast(false)} /> : null}
  </>;
}
