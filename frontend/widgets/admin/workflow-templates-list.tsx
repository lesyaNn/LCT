'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import AddLarge from '@atomaro/icons/24/action/AddLarge';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { useQuery } from '@tanstack/react-query';
import { useCreateWorkflowTemplate } from '@/shared/lib/workflow-template-mutations';
import { listWorkflowTemplates, workflowTemplateListQueryKey, type CreateWorkflowTemplateInput } from '@/shared/lib/workflow-templates-repository';
import { Button } from '@/shared/ui/rtk/button';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { CreateTemplateModal } from './workflow-template-modals';
import styles from './workflow-template-editor.module.css';

export function WorkflowTemplatesList() {
  const router = useRouter();
  const query = useQuery({ queryKey: workflowTemplateListQueryKey(), queryFn: ({ signal }) => listWorkflowTemplates(1, 100, signal), staleTime: 30_000 });
  const createTemplate = useCreateWorkflowTemplate();
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const create = async (input: CreateWorkflowTemplateInput) => {
    setCreateError(null);
    try {
      const template = await createTemplate.mutateAsync(input);
      router.push(`/admin/workflow/templates/${template.id}/edit`);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : 'Не удалось создать шаблон.');
    }
  };

  if (query.isError) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <div className={styles.page}><nav className={styles.localBreadcrumbs} aria-label="Хлебные крошки"><Link href="/admin">Администрирование</Link><span aria-hidden="true">/</span><span aria-current="page">Шаблоны Workflow</span></nav><header className={styles.editorHeader}><div><p className={styles.eyebrow}>Администрирование</p><h1>Шаблоны Workflow</h1><p className={styles.description}>Управляйте набором и порядком этапов для новых процессов.</p></div><Button type="button" variant="primary" size="m" onClick={() => { setCreateError(null); setCreateOpen(true); }}><AddLarge size={18} fill="currentColor" />Новый шаблон</Button></header><section className={styles.templateSurface} aria-labelledby="templates-heading"><div className={styles.surfaceHeader}><div><h2 id="templates-heading">Все шаблоны</h2><p>{query.data ? `Всего: ${query.data.total}` : 'Загрузка…'}</p></div></div>{query.isPending ? <div className={styles.listSkeleton} aria-busy="true">{Array.from({ length: 4 }, (_, index) => <span key={index} />)}</div> : query.data?.items.length ? <ul className={styles.templateList}>{query.data.items.map((template) => <li key={template.id}><div><div className={styles.templateTitle}><h3>{template.name}</h3><span className={template.isActive ? styles.activeBadge : styles.inactiveBadge}>{template.isActive ? 'Активен' : 'Отключён'}</span></div>{template.description ? <p>{template.description}</p> : <p className={styles.muted}>Без описания</p>}</div><Link className={styles.editLink} href={`/admin/workflow/templates/${template.id}/edit`}>Редактировать<ArrowRight size={18} fill="currentColor" /></Link></li>)}</ul> : <div className={styles.emptyState}><h3>Шаблонов пока нет</h3><p>Создайте первый шаблон и добавьте в него этапы.</p><Button type="button" variant="primary" size="m" onClick={() => setCreateOpen(true)}><AddLarge size={18} fill="currentColor" />Новый шаблон</Button></div>}</section>{createOpen ? <CreateTemplateModal pending={createTemplate.isPending} error={createError} onClose={() => { if (!createTemplate.isPending) setCreateOpen(false); }} onSubmit={create} /> : null}</div>;
}
