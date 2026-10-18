'use client';

import { useRef, useState } from 'react';
import Trash from '@atomaro/icons/24/action/Trash';
import { normalizeApiError } from '@/shared/lib/api-errors';
import type { WorkflowTemplateStage } from '@/shared/lib/workflow-templates-repository';
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

  return <Modal title="Задачи этапа по умолчанию" onClose={() => { if (!pending) onClose(); }}>
    <form className={styles.modalForm} onSubmit={(event) => { event.preventDefault(); if (!pending) void save(); }}>
      <p className={styles.defaultTasksHint}>Этап «{stage.name}». Эти задачи появятся в разделе «Задачи этапа» при запуске нового Workflow. Изменения не затронут уже запущенные процессы.</p>
      {tasks.length ? <ol className={styles.defaultTaskList}>{tasks.map((task, index) => <li key={task.id} className={styles.defaultTaskRow}>
        <Input aria-label={`Название задачи ${index + 1}`} value={task.title} maxLength={512} required disabled={pending} onChange={(event) => { setTasks((current) => current.map((item) => item.id === task.id ? { ...item, title: event.target.value } : item)); setError(null); }} />
        <IconButton icon={<Trash size={18} fill="currentColor" />} label={`Удалить задачу ${index + 1}`} intent="danger" size={18} disabled={pending} onClick={() => setTasks((current) => current.filter((item) => item.id !== task.id))} />
      </li>)}</ol> : <p className={styles.defaultTasksHint}>Задач по умолчанию пока нет.</p>}
      <Button type="button" variant="secondary" size="s" disabled={pending} onClick={() => { const id = nextId.current++; setTasks((current) => [...current, { id, title: '' }]); }}>Добавить задачу</Button>
      {error ? <p className={styles.inlineError} role="alert">{error}</p> : null}
      <div className={styles.modalActions}>
        <Button type="button" variant="ghost" size="m" disabled={pending} onClick={onClose}>Отмена</Button>
        <Button type="submit" variant="primary" size="m" loading={pending} disabled={pending}>Сохранить</Button>
      </div>
    </form>
  </Modal>;
}
