'use client';

import { useId, useRef, useState } from 'react';
import AddSmall from '@atomaro/icons/24/action/AddSmall';
import Checklist from '@atomaro/icons/24/action/Checklist';
import Trash from '@atomaro/icons/24/action/Trash';
import { normalizeApiError } from '@/shared/lib/api-errors';
import type { WorkflowTemplateStage } from '@/shared/lib/workflow-templates-repository';
import { StateView } from '@/shared/ui/state-view';
import { Button } from '@/shared/ui/rtk/button';
import { Input } from '@/shared/ui/rtk/form-controls';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Modal } from '@/shared/ui/rtk/modal';
import styles from './workflow-template-editor.module.css';

export function StageDefaultTasksModal({ stage, pending, onClose, onSave }: {
  stage: WorkflowTemplateStage;
  pending: boolean;
  onClose: () => void;
  onSave: (tasks: string[]) => Promise<void>;
}) {
  const [tasks, setTasks] = useState(() => stage.defaultTasks.map((title, id) => ({ id, title })));
  const formId = useId();
  const nextId = useRef(tasks.length);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    const titles = tasks.map((task) => task.title.trim());
    if (titles.some((title) => !title)) {
      setError('Укажите название каждой задачи или удалите пустую строку.');
      return;
    }
    setError(null);
    try {
      await onSave(titles);
      onClose();
    } catch (cause) {
      setError(normalizeApiError(cause).message);
    }
  };

  const addTask = () => { const id = nextId.current++; setTasks((current) => [...current, { id, title: '' }]); };

  return <Modal title="Задачи этапа по умолчанию" size="l" onClose={() => { if (!pending) onClose(); }} footer={<div className={styles.defaultTasksFooter}>
    <Button type="button" variant="secondary" size="m" disabled={pending} onClick={onClose}>Отмена</Button>
    <Button type="submit" form={formId} variant="primary" size="m" loading={pending} disabled={pending}>Сохранить</Button>
  </div>}>
    <form id={formId} className={styles.defaultTasksForm} onSubmit={(event) => { event.preventDefault(); if (!pending) void save(); }}>
      <div className={styles.defaultTasksIntro}>
        <p>Этап «{stage.name}». Эти задачи появятся в разделе «Задачи этапа» при запуске нового Workflow.</p>
        <p className={styles.defaultTasksNote}>Изменения не затронут уже запущенные процессы.</p>
      </div>
      {tasks.length ? <><ol className={styles.defaultTaskList}>{tasks.map((task, index) => <li key={task.id} className={styles.defaultTaskRow}>
        <Input aria-label={`Название задачи ${index + 1}`} value={task.title} maxLength={512} required disabled={pending} onChange={(event) => { setTasks((current) => current.map((item) => item.id === task.id ? { ...item, title: event.target.value } : item)); setError(null); }} />
        <IconButton icon={<Trash size={18} fill="currentColor" />} label={`Удалить задачу ${index + 1}`} intent="danger" size={18} disabled={pending} onClick={() => setTasks((current) => current.filter((item) => item.id !== task.id))} />
      </li>)}</ol><Button type="button" variant="secondary" size="m" disabled={pending} onClick={addTask}><AddSmall size={18} fill="currentColor" aria-hidden="true" />Добавить задачу</Button></> : <StateView className={styles.defaultTasksEmpty} presentation="compact" headingLevel={3} ariaLive="off" title="Задач по умолчанию пока нет" icon={<Checklist size={24} fill="currentColor" />} actions={<Button type="button" variant="secondary" size="m" disabled={pending} onClick={addTask}><AddSmall size={18} fill="currentColor" aria-hidden="true" />Добавить задачу</Button>} />}
      {error ? <p className={styles.inlineError} role="alert">{error}</p> : null}
    </form>
  </Modal>;
}
