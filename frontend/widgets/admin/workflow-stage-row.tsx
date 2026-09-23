'use client';

import { useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import ArrowUp from '@atomaro/icons/24/navigation/ArrowUp';
import ArrowDown from '@atomaro/icons/24/navigation/ArrowDown';
import DragVerticalDots from '@atomaro/icons/24/editor/DragVerticalDots';
import Edit from '@atomaro/icons/24/editor/Edit';
import Trash from '@atomaro/icons/24/action/Trash';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Input, NumberStepper, Switch } from '@/shared/ui/rtk/form-controls';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { normalizeApiError } from '@/shared/lib/api-errors';
import type { UpdateWorkflowStageInput, WorkflowTemplateStage } from '@/shared/lib/workflow-templates-repository';
import styles from './workflow-template-editor.module.css';

interface WorkflowStageRowProps {
  stage: WorkflowTemplateStage;
  index: number;
  count: number;
  saving: boolean;
  orderDirty: boolean;
  onMove: (fromIndex: number, toIndex: number) => void;
  onUpdate: (stageId: string, patch: UpdateWorkflowStageInput, successTitle?: string) => Promise<void>;
  onDelete: (stage: WorkflowTemplateStage) => void;
}

export function WorkflowStageRow({ stage, index, count, saving, orderDirty, onMove, onUpdate, onDelete }: WorkflowStageRowProps) {
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(stage.name);
  const [nameError, setNameError] = useState('');
  const [slaDraft, setSlaDraft] = useState(stage.slaDays);
  const savingNameRef = useRef(false);
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging, isOver } = useSortable({ id: stage.id, disabled: saving });
  const style = { transform: CSS.Transform.toString(transform), transition } satisfies CSSProperties;

  const cancelName = () => {
    setNameDraft(stage.name);
    setNameError('');
    setEditingName(false);
  };

  const saveName = async () => {
    if (savingNameRef.current) return;
    const name = nameDraft.trim();
    if (!name) {
      setNameError('Название не может быть пустым.');
      return;
    }
    if (name === stage.name.trim()) {
      cancelName();
      return;
    }
    setNameError('');
    savingNameRef.current = true;
    try {
      await onUpdate(stage.id, { name }, 'Название этапа изменено');
      setEditingName(false);
    } catch (cause) {
      const normalized = normalizeApiError(cause, { defaultCode: 'DUPLICATE_ENTITY' });
      setNameError(normalized.code === 'DUPLICATE_ENTITY' ? 'Этап с таким названием уже существует.' : normalized.message);
    } finally {
      savingNameRef.current = false;
    }
  };

  const handleNameKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      void saveName();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      cancelName();
    }
  };

  const commitSla = async (value: number | null) => {
    if (value === stage.slaDays) return;
    try {
      await onUpdate(stage.id, { slaDays: value });
    } catch {
      setSlaDraft(stage.slaDays);
    }
  };

  return <li ref={setNodeRef} className={`${styles.stageRow} ${isDragging ? styles.dragging : ''} ${isOver && !isDragging ? styles.dragOver : ''} ${!stage.isActive ? styles.inactiveRow : ''}`} style={style} aria-busy={saving}>
    <div className={styles.dragCell}>
      <Tooltip content="Перетащите или нажмите Space, затем стрелки">
        <button ref={setActivatorNodeRef} className={styles.dragHandle} type="button" disabled={saving} aria-label={`Переместить этап «${stage.name}»`} {...attributes} {...listeners}><DragVerticalDots size={20} fill="currentColor" /></button>
      </Tooltip>
    </div>
    <span className={styles.orderCell} data-label="№">{index + 1}</span>
    <div className={styles.nameCell} data-label="Название">
      {editingName ? <div className={styles.nameEditor}><Input autoFocus value={nameDraft} maxLength={512} required aria-required="true" disabled={saving} aria-label={`Название этапа ${index + 1}`} aria-invalid={Boolean(nameError)} aria-describedby={nameError ? `${stage.id}-name-error` : undefined} onFocus={(event) => event.currentTarget.select()} onChange={(event) => { setNameDraft(event.target.value); if (nameError) setNameError(''); }} onKeyDown={handleNameKeyDown} onBlur={() => { if (!saving) void saveName(); }} /><IconButton icon={<CheckLarge size={18} fill="currentColor" />} label="Сохранить название" size={18} disabled={saving} onMouseDown={(event) => event.preventDefault()} onClick={() => void saveName()} /><IconButton icon={<CloseLarge size={18} fill="currentColor" />} label="Отменить редактирование" size={18} disabled={saving} onMouseDown={(event) => event.preventDefault()} onClick={cancelName} />{nameError ? <small id={`${stage.id}-name-error`} className={styles.inlineError} role="alert">{nameError}</small> : null}</div> : <div className={styles.nameDisplay}><span>{stage.name}</span>{stage.description ? <small>{stage.description}</small> : null}<IconButton icon={<Edit size={18} fill="currentColor" />} label={`Изменить название этапа «${stage.name}»`} size={18} disabled={saving || orderDirty} onClick={() => { setNameDraft(stage.name); setNameError(''); setEditingName(true); }} /></div>}
    </div>
    <div className={styles.controlCell} data-label="Обязательный"><Switch checked={stage.isRequired} label={`Этап «${stage.name}» обязательный`} disabled={saving || orderDirty} onChange={(checked) => { void onUpdate(stage.id, { isRequired: checked }).catch(() => undefined); }} /></div>
    <div className={styles.controlCell} data-label="Активный"><Switch checked={stage.isActive} label={`Этап «${stage.name}» активен`} disabled={saving || orderDirty} onChange={(checked) => { void onUpdate(stage.id, { isActive: checked }, checked ? 'Этап включён' : 'Этап отключён').catch(() => undefined); }} /></div>
    <div className={styles.daysCell} data-label="Оценка дней"><NumberStepper value={slaDraft} label={`Оценка дней для этапа «${stage.name}»`} disabled={saving || orderDirty} onChange={setSlaDraft} onCommit={(value) => void commitSla(value)} /></div>
    <div className={styles.actionsCell} data-label="Действия">
      <IconButton icon={<ArrowUp size={18} fill="currentColor" />} label={`Переместить этап «${stage.name}» вверх`} size={18} disabled={saving || index === 0} onClick={() => onMove(index, index - 1)} />
      <IconButton icon={<ArrowDown size={18} fill="currentColor" />} label={`Переместить этап «${stage.name}» вниз`} size={18} disabled={saving || index === count - 1} onClick={() => onMove(index, index + 1)} />
      {stage.isActive ? <Tooltip content="Мягкое удаление: этап будет отключён"><IconButton icon={<Trash size={18} fill="currentColor" />} label={`Удалить этап «${stage.name}»`} size={18} disabled={saving || orderDirty} className={styles.deleteButton} onClick={() => onDelete(stage)} /></Tooltip> : <span className={styles.inactiveLabel}>Отключён</span>}
      {saving ? <span className={styles.rowSaving} role="status">Сохранение…</span> : null}
    </div>
  </li>;
}
