'use client';

import { useId, useMemo, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { applyServerErrorsToForm, normalizeApiError, type NormalizedApiError } from '@/shared/lib/api-errors';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Input, NumberStepper, Select, Switch, TextArea } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import type { CreateWorkflowStageInput, CreateWorkflowTemplateInput, WorkflowTemplateStage } from '@/shared/lib/workflow-templates-repository';
import styles from './workflow-template-editor.module.css';

const NAME_MAX_LENGTH = 512;
const trimmedRequiredName = (message: string) => z.string().max(NAME_MAX_LENGTH, `Максимум ${NAME_MAX_LENGTH} символов.`).refine((value) => value.trim().length > 0, message);

const createTemplateSchema = z.object({
  name: trimmedRequiredName('Укажите название шаблона.'),
  description: z.string(),
});

const addStageBaseSchema = z.object({
  name: trimmedRequiredName('Укажите название этапа.'),
  description: z.string(),
  isRequired: z.boolean(),
  slaDays: z.number().int('Укажите целое число дней.').min(1, 'Оценка должна быть не менее 1 дня.').nullable(),
  position: z.string().min(1, 'Выберите позицию.'),
});

type CreateTemplateValues = z.infer<typeof createTemplateSchema>;
type AddStageValues = z.infer<typeof addStageBaseSchema>;

const addStageFields = ['name', 'description', 'slaDays', 'position'] as const;
const createTemplateFields = ['name', 'description'] as const;

function describedBy(error?: string, errorId?: string): string | undefined {
  return error ? errorId : undefined;
}

export function AddStageModal({ stages, pending, onClose, onSubmit, onError }: { stages: WorkflowTemplateStage[]; pending: boolean; onClose: () => void; onSubmit: (input: CreateWorkflowStageInput) => Promise<void>; onError?: (error: NormalizedApiError) => void }) {
  const id = useId();
  const [serverFormError, setServerFormError] = useState<string | null>(null);
  const validPositions = useMemo(() => new Set(['end', ...stages.map((stage) => stage.id)]), [stages]);
  const schema = useMemo(() => addStageBaseSchema.refine((values) => validPositions.has(values.position), { path: ['position'], message: 'Выберите доступную позицию.' }), [validPositions]);
  const { register, control, handleSubmit, setError, setFocus, formState: { errors, submitCount } } = useForm<AddStageValues>({
    resolver: zodResolver(schema),
    mode: 'onBlur',
    reValidateMode: 'onChange',
    defaultValues: { name: '', description: '', isRequired: true, slaDays: null, position: 'end' },
  });
  const showBanner = Boolean(serverFormError || (submitCount > 0 && Object.keys(errors).length));

  const submit = handleSubmit(async (values) => {
    setServerFormError(null);
    const previousStage = stages.find((stage) => stage.id === values.position);
    try {
      await onSubmit({
        name: values.name.trim(),
        description: values.description.trim() || null,
        isRequired: values.isRequired,
        slaDays: values.slaDays,
        orderIndex: previousStage ? previousStage.orderIndex + 1 : undefined,
      });
    } catch (cause) {
      const normalized = normalizeApiError(cause, { defaultCode: 'DUPLICATE_ENTITY' });
      if (normalized.code === 'DUPLICATE_ENTITY') {
        setError('name', { type: 'server', message: 'Этап с таким названием уже существует.' });
        setFocus('name');
        setServerFormError('Исправьте ошибки в форме.');
        return;
      }
      const mapped = applyServerErrorsToForm(normalized, { fields: addStageFields, fieldMap: { order_index: 'position', sla_days: 'slaDays', is_required: 'isRequired' }, setError, setFocus });
      if (normalized.kind === 'validation') setServerFormError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : 'Исправьте ошибки в форме.');
      else onError?.(normalized);
    }
  });

  const nameId = `${id}-stage-name`;
  const nameErrorId = `${nameId}-error`;
  const descriptionId = `${id}-stage-description`;
  const slaId = `${id}-stage-sla`;
  const slaErrorId = `${slaId}-error`;
  const positionId = `${id}-stage-position`;
  const positionErrorId = `${positionId}-error`;
  return <Modal title="Добавить этап" onClose={onClose}><form className={styles.modalForm} onSubmit={submit} noValidate>{showBanner ? <FormErrorBanner>{serverFormError ?? undefined}</FormErrorBanner> : null}<FormField label="Название" htmlFor={nameId} required error={errors.name?.message} errorId={nameErrorId}><Input id={nameId} autoFocus maxLength={NAME_MAX_LENGTH} required aria-required="true" disabled={pending} aria-invalid={Boolean(errors.name)} aria-describedby={describedBy(errors.name?.message, nameErrorId)} {...register('name')} /></FormField><FormField label="Описание" htmlFor={descriptionId} errorId={`${descriptionId}-error`}><TextArea id={descriptionId} rows={4} disabled={pending} {...register('description')} /></FormField><div className={styles.modalGrid}><div className={styles.switchField}><span>Обязательный</span><Controller control={control} name="isRequired" render={({ field }) => <Switch checked={field.value} label="Обязательный этап" disabled={pending} onChange={field.onChange} />} /></div><FormField label="Оценка дней" htmlFor={slaId} error={errors.slaDays?.message} errorId={slaErrorId}><Controller control={control} name="slaDays" render={({ field }) => <NumberStepper value={field.value} min={1} label="Оценка дней" disabled={pending} inputRef={field.ref} ariaInvalid={Boolean(errors.slaDays)} ariaDescribedBy={describedBy(errors.slaDays?.message, slaErrorId)} onChange={field.onChange} onCommit={field.onChange} />} /></FormField></div><FormField label="Позиция" htmlFor={positionId} error={errors.position?.message} errorId={positionErrorId}><Select id={positionId} disabled={pending} aria-invalid={Boolean(errors.position)} aria-describedby={describedBy(errors.position?.message, positionErrorId)} {...register('position')}><option value="end">В конец</option>{stages.map((stage, index) => <option value={stage.id} key={stage.id}>{`После ${index + 1}. «${stage.name}»`}</option>)}</Select></FormField><div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={pending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" size="m" disabled={pending} aria-busy={pending}>{pending ? 'Добавление…' : 'Добавить'}</Button></div></form></Modal>;
}

export function CreateTemplateModal({ pending, onClose, onSubmit, onError }: { pending: boolean; onClose: () => void; onSubmit: (input: CreateWorkflowTemplateInput) => Promise<void>; onError?: (error: NormalizedApiError) => void }) {
  const id = useId();
  const [serverFormError, setServerFormError] = useState<string | null>(null);
  const { register, handleSubmit, setError, setFocus, formState: { errors, submitCount } } = useForm<CreateTemplateValues>({ resolver: zodResolver(createTemplateSchema), mode: 'onBlur', reValidateMode: 'onChange', defaultValues: { name: '', description: '' } });
  const submit = handleSubmit(async (values) => {
    setServerFormError(null);
    try {
      await onSubmit({ name: values.name.trim(), description: values.description.trim() || null });
    } catch (cause) {
      const normalized = normalizeApiError(cause, { defaultCode: 'DUPLICATE_ENTITY' });
      if (normalized.code === 'DUPLICATE_ENTITY') {
        setError('name', { type: 'server', message: 'Шаблон с таким названием уже существует.' });
        setFocus('name');
        setServerFormError('Исправьте ошибки в форме.');
        return;
      }
      const mapped = applyServerErrorsToForm(normalized, { fields: createTemplateFields, setError, setFocus });
      if (normalized.kind === 'validation') setServerFormError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : 'Исправьте ошибки в форме.');
      else onError?.(normalized);
    }
  });
  const nameId = `${id}-template-name`;
  const nameErrorId = `${nameId}-error`;
  const descriptionId = `${id}-template-description`;
  const showBanner = Boolean(serverFormError || (submitCount > 0 && Object.keys(errors).length));
  return <Modal title="Новый шаблон Workflow" onClose={onClose}><form className={styles.modalForm} onSubmit={submit} noValidate>{showBanner ? <FormErrorBanner>{serverFormError ?? undefined}</FormErrorBanner> : null}<FormField label="Название" htmlFor={nameId} required error={errors.name?.message} errorId={nameErrorId}><Input id={nameId} autoFocus maxLength={NAME_MAX_LENGTH} required aria-required="true" disabled={pending} aria-invalid={Boolean(errors.name)} aria-describedby={describedBy(errors.name?.message, nameErrorId)} {...register('name')} /></FormField><FormField label="Описание" htmlFor={descriptionId} errorId={`${descriptionId}-error`}><TextArea id={descriptionId} rows={5} disabled={pending} {...register('description')} /></FormField><div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={pending} onClick={onClose}>Отмена</Button><Button type="submit" variant="primary" size="m" disabled={pending}>{pending ? 'Создание…' : 'Создать'}</Button></div></form></Modal>;
}

export function StageConfirmationModal({ stage, mode, pending, error, onClose, onConfirm }: { stage: WorkflowTemplateStage; mode: 'disable' | 'delete'; pending: boolean; error: string | null; onClose: () => void; onConfirm: () => void }) {
  const title = mode === 'delete' ? 'Удалить этап?' : 'Отключить этап?';
  return <Modal title={title} onClose={onClose}><div className={styles.confirmation}><p><strong>{stage.name}</strong> будет отключён в шаблоне и не войдёт в новые процессы.</p><p className={styles.confirmationNote}>Уже созданные Workflow хранят снимок этапов и не изменятся.</p>{error ? <FormErrorBanner>{error}</FormErrorBanner> : null}<div className={styles.modalActions}><Button type="button" variant="ghost" size="m" disabled={pending} onClick={onClose}>Отмена</Button><Button type="button" variant={mode === 'delete' ? 'danger' : 'primary'} size="m" disabled={pending} onClick={onConfirm}>{pending ? 'Сохранение…' : mode === 'delete' ? 'Удалить' : 'Отключить'}</Button></div></div></Modal>;
}
