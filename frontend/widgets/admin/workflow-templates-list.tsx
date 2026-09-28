'use client';

import { visibleWorkflowDescription } from '@/shared/lib/visible-workflow-description';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import AddLarge from '@atomaro/icons/24/action/AddLarge';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { useQuery } from '@tanstack/react-query';
import { useCreateWorkflowTemplate, useDeleteWorkflowTemplate, useUpdateWorkflowTemplate } from '@/shared/lib/workflow-template-mutations';
import { normalizeApiError, type NormalizedApiError } from '@/shared/lib/api-errors';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { listWorkflowTemplates, workflowTemplateListQueryKey, type CreateWorkflowTemplateInput } from '@/shared/lib/workflow-templates-repository';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { ListSkeleton } from '@/shared/ui/skeleton';
import { Toast } from '@/shared/ui/rtk/toast';
import { Modal } from '@/shared/ui/rtk/modal';
import { FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { CreateTemplateModal } from './workflow-template-modals';
import styles from './workflow-template-editor.module.css';

export function WorkflowTemplatesList() {
  const demoMode = isMockDataSourceFor('workflow');
  const router = useRouter();
  const query = useQuery({ queryKey: workflowTemplateListQueryKey(), queryFn: ({ signal }) => listWorkflowTemplates(1, 100, signal), staleTime: 30_000 });
  const createTemplate = useCreateWorkflowTemplate();
  const updateTemplate = useUpdateWorkflowTemplate();
  const deleteTemplate = useDeleteWorkflowTemplate();
  const [createOpen, setCreateOpen] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [notification, setNotification] = useState<NormalizedApiError | null>(null);
  const [retireCandidate, setRetireCandidate] = useState<{ id: string; name: string } | null>(null);
  const [retireError, setRetireError] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<{ id: string; name: string } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const retire = async () => {
    if (!retireCandidate) return;
    try {
      await updateTemplate.mutateAsync({ templateId: retireCandidate.id, patch: { isActive: false } });
      setRetireCandidate(null);
      setRetireError(null);
    } catch (cause) {
      setRetireError(normalizeApiError(cause).message);
    }
  };

  const create = async (input: CreateWorkflowTemplateInput) => {
    const template = await createTemplate.mutateAsync(input);
    router.push(`/admin/workflow/templates/${template.id}/edit`);
  };

  const remove = async () => {
    if (!deleteCandidate) return;
    try {
      await deleteTemplate.mutateAsync(deleteCandidate.id);
      setDeleteCandidate(null);
      setDeleteError(null);
    } catch (cause) {
      setDeleteError(normalizeApiError(cause).message);
    }
  };

  if (query.isError && !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  const visibleTemplates = query.data?.items.filter((template) => showInactive || template.isActive) ?? [];
  const inactiveCount = query.data?.items.filter((template) => !template.isActive).length ?? 0;

  return <div className={styles.page}>
    <header className={styles.editorHeader}><div><h1>Шаблоны Workflow</h1><p className={styles.description}>Управляйте набором и порядком этапов для новых процессов.</p></div><Button type="button" variant="primary" size="m" onClick={() => setCreateOpen(true)}><AddLarge size={18} fill="currentColor" />Новый шаблон</Button></header>
    <section className={styles.templateSurface} aria-labelledby="templates-heading">
      <div className={styles.surfaceHeader}><div><h2 id="templates-heading">Шаблоны Workflow</h2><p>{query.data ? `Активных: ${query.data.items.length - inactiveCount}` : 'Загрузка…'}</p></div>{inactiveCount ? <Button type="button" variant="ghost" size="s" onClick={() => setShowInactive((current) => !current)}>{showInactive ? 'Скрыть отключённые' : `Показать отключённые (${inactiveCount})`}</Button> : null}</div>
      {query.isPending ? <ListSkeleton items={4} withAvatar={false} /> : visibleTemplates.length ? <ul className={styles.templateList}>{visibleTemplates.map((template) => <li key={template.id}>
        <div><div className={styles.templateTitle}><h3>{template.name}</h3><span className={template.isActive ? styles.activeBadge : styles.inactiveBadge}>{template.isActive ? 'Активен' : 'Отключён'}</span></div>{visibleWorkflowDescription(template.description) ? <p>{template.description}</p> : null}</div>
        <div className={styles.headerActions}>
          {!demoMode && template.isActive ? <Button type="button" variant="ghost" size="s" disabled={updateTemplate.isPending} onClick={() => { setRetireError(null); setRetireCandidate({ id: template.id, name: template.name }); }}>Отключить</Button> : null}
          {!demoMode && !template.isActive ? <Button type="button" variant="ghost" size="s" disabled={updateTemplate.isPending} onClick={() => void updateTemplate.mutateAsync({ templateId: template.id, patch: { isActive: true } }).catch((cause) => setNotification(normalizeApiError(cause)))}>Активировать</Button> : null}
          {!demoMode ? <Button type="button" variant="ghost" size="s" disabled={deleteTemplate.isPending} onClick={() => { setDeleteError(null); setDeleteCandidate({ id: template.id, name: template.name }); }}>Удалить</Button> : null}
          <Link className={styles.editLink} href={`/admin/workflow/templates/${template.id}/edit`}>Редактировать<ArrowRight size={18} fill="currentColor" /></Link>
        </div>
      </li>)}</ul> : <EmptyState title="Шаблонов пока нет" description="Создайте первый шаблон и добавьте в него этапы." headingLevel={3} primaryAction={{ label: 'Новый шаблон', onClick: () => setCreateOpen(true) }} />}
    </section>
    {createOpen ? <CreateTemplateModal pending={createTemplate.isPending} onClose={() => { if (!createTemplate.isPending) setCreateOpen(false); }} onSubmit={create} onError={(error) => setNotification(error)} /> : null}
    {retireCandidate ? <Modal title="Отключить шаблон Workflow?" onClose={() => { if (!updateTemplate.isPending) setRetireCandidate(null); }}><div className={styles.confirmation}><p><strong>{retireCandidate.name}</strong> больше не будет доступен для новых Workflow.</p><p>Существующие Workflow сохранят свои этапы и историю. Шаблон можно активировать снова.</p>{retireError ? <FormErrorBanner>{retireError}</FormErrorBanner> : null}<div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={updateTemplate.isPending} onClick={() => setRetireCandidate(null)}>Отмена</Button><Button type="button" variant="danger" size="m" loading={updateTemplate.isPending} disabled={updateTemplate.isPending} onClick={() => void retire()}>Отключить</Button></div></div></Modal> : null}
    {deleteCandidate ? <Modal title="Удалить шаблон Workflow?" onClose={() => { if (!deleteTemplate.isPending) setDeleteCandidate(null); }}><div className={styles.confirmation}><p>Шаблон «{deleteCandidate.name}» и его этапы будут удалены без возможности восстановления.</p><p>Если по нему уже запущены Workflow, удаление будет запрещено. Такой шаблон можно отключить.</p>{deleteError ? <FormErrorBanner>{deleteError}</FormErrorBanner> : null}<div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={deleteTemplate.isPending} onClick={() => setDeleteCandidate(null)}>Отмена</Button><Button type="button" variant="danger" size="m" loading={deleteTemplate.isPending} disabled={deleteTemplate.isPending} onClick={() => void remove()}>Удалить шаблон</Button></div></div></Modal> : null}
    {notification ? <div className={styles.toastViewport}><Toast intent="error" title="Не удалось сохранить шаблон" message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </div>;
}
