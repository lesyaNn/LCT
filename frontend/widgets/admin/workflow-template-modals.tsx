'use client';

import { useRef, useState, type FormEvent } from 'react';
import { Button } from '@/shared/ui/rtk/button';
import { Input, NumberStepper, Select, Switch, TextArea } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import type { CreateWorkflowStageInput, CreateWorkflowTemplateInput, WorkflowTemplateStage } from '@/shared/lib/workflow-templates-repository';
import styles from './workflow-template-editor.module.css';

const NAME_MAX_LENGTH = 512;

function Field({ label, required = false, error, children }: { label: string; required?: boolean; error?: string; children: React.ReactNode }) {
  return <label className={styles.field}><span>{label}{required ? <sup aria-hidden="true"> *</sup> : null}</span>{children}{error ? <small className={styles.fieldError} role="alert">{error}</small> : null}</label>;
}

export function AddStageModal({ stages, pending, error, onClose, onSubmit }: { stages: WorkflowTemplateStage[]; pending: boolean; error: string | null; onClose: () => void; onSubmit: (input: CreateWorkflowStageInput) => Promise<void> }) {
  const nameRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isRequired, setIsRequired] = useState(true);
  const [slaDays, setSlaDays] = useState<number | null>(null);
  const [position, setPosition] = useState('end');
  const [nameError, setNameError] = useState('');
  const [slaError, setSlaError] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setNameError('Укажите название этапа.');
      nameRef.current?.focus();
      return;
    }
    if (slaDays !== null && slaDays < 1) {
      setSlaError('Оценка должна быть не менее 1 дня.');
      return;
    }
    setNameError('');
    setSlaError('');
    const previousStage = stages.find((stage) => stage.id === position);
    void onSubmit({
      name: trimmedName,
      description: description.trim() || null,
      isRequired,
      slaDays,
      orderIndex: previousStage ? previousStage.orderIndex + 1 : undefined,
    });
  };

  return <Modal title="Добавить этап" onClose={onClose} initialFocusRef={nameRef}><form className={styles.modalForm} onSubmit={submit} noValidate><Field label="Название" required error={nameError}><Input ref={nameRef} value={name} maxLength={NAME_MAX_LENGTH} required aria-required="true" disabled={pending} aria-invalid={Boolean(nameError)} onChange={(event) => { setName(event.target.value); if (nameError) setNameError(''); }} /></Field><Field label="Описание"><TextArea value={description} rows={4} disabled={pending} onChange={(event) => setDescription(event.target.value)} /></Field><div className={styles.modalGrid}><div className={styles.switchField}><span>Обязательный</span><Switch checked={isRequired} label="Обязательный этап" disabled={pending} onChange={setIsRequired} /></div><Field label="Оценка дней" error={slaError}><NumberStepper value={slaDays} min={1} label="Оценка дней" disabled={pending} onChange={(value) => { setSlaDays(value); if (slaError) setSlaError(''); }} onCommit={setSlaDays} /></Field></div><Field label="Позиция"><Select value={position} disabled={pending} onChange={(event) => setPosition(event.target.value)}><option value="end">В конец</option>{stages.map((stage, index) => <option value={stage.id} key={stage.id}>{`После ${index + 1}. «${stage.name}»`}</option>)}</Select></Field>{error ? <p className={styles.formError} role="alert">{error}</p> : null}<div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={pending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" size="m" disabled={pending} aria-busy={pending}>{pending ? 'Добавление…' : 'Добавить'}</Button></div></form></Modal>;
}

export function CreateTemplateModal({ pending, error, onClose, onSubmit }: { pending: boolean; error: string | null; onClose: () => void; onSubmit: (input: CreateWorkflowTemplateInput) => Promise<void> }) {
  const nameRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [nameError, setNameError] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setNameError('Укажите название шаблона.');
      nameRef.current?.focus();
      return;
    }
    setNameError('');
    void onSubmit({ name: trimmedName, description: description.trim() || null });
  };

  return <Modal title="Новый шаблон Workflow" onClose={onClose} initialFocusRef={nameRef}><form className={styles.modalForm} onSubmit={submit} noValidate><Field label="Название" required error={nameError}><Input ref={nameRef} value={name} maxLength={NAME_MAX_LENGTH} disabled={pending} aria-invalid={Boolean(nameError)} onChange={(event) => { setName(event.target.value); if (nameError) setNameError(''); }} /></Field><Field label="Описание"><TextArea value={description} rows={5} disabled={pending} onChange={(event) => setDescription(event.target.value)} /></Field>{error ? <p className={styles.formError} role="alert">{error}</p> : null}<div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={pending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" size="m" disabled={pending}>{pending ? 'Создание…' : 'Создать'}</Button></div></form></Modal>;
}

export function StageConfirmationModal({ stage, mode, pending, error, onClose, onConfirm }: { stage: WorkflowTemplateStage; mode: 'disable' | 'delete'; pending: boolean; error: string | null; onClose: () => void; onConfirm: () => void }) {
  const title = mode === 'delete' ? 'Удалить этап?' : 'Отключить этап?';
  return <Modal title={title} onClose={onClose}><div className={styles.confirmation}><p><strong>{stage.name}</strong> будет отключён в шаблоне и не войдёт в новые процессы.</p><p className={styles.confirmationNote}>Уже созданные Workflow хранят снимок этапов и не изменятся.</p>{error ? <p className={styles.formError} role="alert">{error}</p> : null}<div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={pending} onClick={onClose}>Отмена</Button><Button type="button" variant={mode === 'delete' ? 'danger' : 'primary'} size="m" disabled={pending} onClick={onConfirm}>{pending ? 'Сохранение…' : mode === 'delete' ? 'Удалить' : 'Отключить'}</Button></div></div></Modal>;
}
