'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import AddLarge from '@atomaro/icons/24/action/AddLarge';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { useQuery } from '@tanstack/react-query';
import { useCreateWorkflowTemplate } from '@/shared/lib/workflow-template-mutations';
import { type NormalizedApiError } from '@/shared/lib/api-errors';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { listWorkflowTemplates, workflowTemplateListQueryKey, type CreateWorkflowTemplateInput } from '@/shared/lib/workflow-templates-repository';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { ListSkeleton } from '@/shared/ui/skeleton';
import { Toast } from '@/shared/ui/rtk/toast';
import { CreateTemplateModal } from './workflow-template-modals';
import styles from './workflow-template-editor.module.css';

export function WorkflowTemplatesList() {
  const readOnly = !isMockDataSourceFor('workflow');
  const router = useRouter();
  const query = useQuery({ queryKey: workflowTemplateListQueryKey(), queryFn: ({ signal }) => listWorkflowTemplates(1, 100, signal), staleTime: 30_000 });
  const createTemplate = useCreateWorkflowTemplate();
  const [createOpen, setCreateOpen] = useState(false);
  const [notification, setNotification] = useState<NormalizedApiError | null>(null);

  const create = async (input: CreateWorkflowTemplateInput) => {
    const template = await createTemplate.mutateAsync(input);
    router.push(`/admin/workflow/templates/${template.id}/edit`);
  };

  if (query.isError) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <div className={styles.page}><header className={styles.editorHeader}><div><h1>Шаблоны Workflow</h1><p className={styles.description}>{readOnly ? 'Шаблоны доступны для просмотра; изменение будет подключено на этапе 6.' : 'Управляйте набором и порядком этапов для новых процессов.'}</p></div><Button type="button" variant="primary" size="m" disabled={readOnly} title={readOnly ? 'Создание будет подключено на этапе 6' : undefined} onClick={() => setCreateOpen(true)}><AddLarge size={18} fill="currentColor" />Новый шаблон</Button></header><section className={styles.templateSurface} aria-labelledby="templates-heading"><div className={styles.surfaceHeader}><div><h2 id="templates-heading">Все шаблоны</h2><p>{query.data ? `Всего: ${query.data.total}` : 'Загрузка…'}</p></div></div>{query.isPending ? <ListSkeleton items={4} withAvatar={false} /> : query.data?.items.length ? <ul className={styles.templateList}>{query.data.items.map((template) => <li key={template.id}><div><div className={styles.templateTitle}><h3>{template.name}</h3><span className={template.isActive ? styles.activeBadge : styles.inactiveBadge}>{template.isActive ? 'Активен' : 'Отключён'}</span></div>{template.description ? <p>{template.description}</p> : <p className={styles.muted}>Без описания</p>}</div><Link className={styles.editLink} href={`/admin/workflow/templates/${template.id}/edit`}>{readOnly ? 'Просмотреть' : 'Редактировать'}<ArrowRight size={18} fill="currentColor" /></Link></li>)}</ul> : <EmptyState title="Шаблонов пока нет" description={readOnly ? 'Шаблоны ещё не созданы.' : 'Создайте первый шаблон и добавьте в него этапы.'} headingLevel={3} primaryAction={readOnly ? undefined : { label: 'Новый шаблон', onClick: () => setCreateOpen(true) }} />}</section>{createOpen && !readOnly ? <CreateTemplateModal pending={createTemplate.isPending} onClose={() => { if (!createTemplate.isPending) setCreateOpen(false); }} onSubmit={create} onError={(error) => setNotification(error)} /> : null}{notification ? <div className={styles.toastViewport}><Toast intent="error" title="Шаблон не создан" message={notification.message} onClose={() => setNotification(null)} /></div> : null}</div>;
}
