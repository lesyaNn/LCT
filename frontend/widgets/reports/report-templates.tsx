'use client';

import BookOpen from '@atomaro/icons/24/culture/BookOpen';
import Trash from '@atomaro/icons/24/action/Trash';
import Play from '@atomaro/icons/24/media/Play';
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Input } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { normalizeApiError } from '@/shared/lib/api-errors';
import {
  createReportTemplate,
  deleteReportTemplate,
  listReportTemplates,
  reportQueryKeys,
  reportRequestFromForm,
  type ReportTemplate,
} from '@/shared/lib/reports-repository';
import type { ReportFormSchema } from './report-form-schema';
import styles from './reports-page.module.css';

interface ReportTemplatesSectionProps {
  currentValues: ReportFormSchema;
  onApply: (template: ReportTemplate) => void;
  saveOpen: boolean;
  onCloseSave: () => void;
}

/** Saved filter/column presets. */
export function ReportTemplatesSection({ currentValues, onApply, saveOpen, onCloseSave }: ReportTemplatesSectionProps) {
  const queryClient = useQueryClient();
  const nameRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const templatesQuery = useQuery({ queryKey: reportQueryKeys.templates, queryFn: listReportTemplates, staleTime: 60_000 });
  const templates = templatesQuery.data ?? [];

  const saveMutation = useMutation({
    mutationFn: (templateName: string) => createReportTemplate(templateName, reportRequestFromForm(currentValues)),
    onSuccess: (template) => {
      queryClient.setQueryData<ReportTemplate[]>(reportQueryKeys.templates, (current = []) => [...current, template]);
      setName('');
      setSaveError(null);
      onCloseSave();
    },
    onError: (cause) => setSaveError(normalizeApiError(cause, { fallbackMessage: 'Не удалось сохранить шаблон.' }).message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteReportTemplate,
    onSuccess: (_, templateId) => {
      queryClient.setQueryData<ReportTemplate[]>(reportQueryKeys.templates, (current = []) => current.filter((template) => template.id !== templateId));
      setDeleteError(null);
    },
    onError: (cause) => setDeleteError(normalizeApiError(cause, { fallbackMessage: 'Не удалось удалить шаблон.' }).message),
  });

  const closeSave = () => {
    if (saveMutation.isPending) return;
    setName('');
    setSaveError(null);
    onCloseSave();
  };

  return (
    <section className={styles.templatesSurface} aria-labelledby="report-templates-heading" tabIndex={0}>
      <div className={styles.templatesHeader}>
        <div className={styles.headingWithIcon}>
          <BookOpen size={20} fill="currentColor" aria-hidden="true" />
          <div>
            <h2 id="report-templates-heading">Шаблоны отчётов</h2>
            <p>Сохраните параметры и применяйте их повторно.</p>
          </div>
        </div>
      </div>
      {templates.length ? (
        <div className={styles.templateList} aria-label="Сохранённые шаблоны">
          {templates.map((template) => (
            <div className={styles.templateItem} key={template.id}>
              <div className={styles.templateInfo}>
                <strong>{template.name}</strong>
                <span className={styles.templateMeta}>{template.isShared ? 'Общий · ' : ''}{template.columns.length} колонок · {template.format.toUpperCase()}</span>
              </div>
              <div className={styles.templateRowActions}>
                <Button variant="ghost" size="s" type="button" aria-label={`Применить шаблон ${template.name}`} onClick={() => onApply(template)}>
                  <Play size={16} fill="currentColor" aria-hidden="true" />
                </Button>
                <Button variant="ghost" size="s" type="button" aria-label={`Удалить шаблон ${template.name}`} onClick={() => deleteMutation.mutate(template.id)}>
                  <Trash size={16} fill="currentColor" aria-hidden="true" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className={styles.muted}>Шаблонов пока нет.</p>
      )}
      {templatesQuery.isError ? (
        <FormErrorBanner>
          Не удалось загрузить шаблоны.{' '}
          <Button type="button" variant="ghost" size="s" onClick={() => void templatesQuery.refetch()}>Повторить</Button>
        </FormErrorBanner>
      ) : null}
      {deleteError ? <FormErrorBanner>{deleteError}</FormErrorBanner> : null}
      {saveOpen ? (
        <Modal title="Сохранить как шаблон" onClose={closeSave} initialFocusRef={nameRef}>
          <form className={styles.saveTemplateForm} onSubmit={(event) => { event.preventDefault(); if (name.trim() && !saveMutation.isPending) saveMutation.mutate(name.trim()); }}>
            <FormField label="Название шаблона" htmlFor="report-template-name" error={saveError ?? undefined} errorId="report-template-name-error">
              <Input
                ref={nameRef}
                id="report-template-name"
                placeholder="Например, ежемесячный отчёт"
                value={name}
                onChange={(event) => { setName(event.target.value); if (saveError) setSaveError(null); }}
                maxLength={256}
                disabled={saveMutation.isPending}
                aria-invalid={Boolean(saveError) || undefined}
                aria-describedby={saveError ? 'report-template-name-error' : undefined}
              />
            </FormField>
            <div className={styles.saveTemplateActions}>
              <Button variant="ghost" size="s" type="button" onClick={closeSave} disabled={saveMutation.isPending}>Отмена</Button>
              <Button variant="primary" size="s" type="submit" loading={saveMutation.isPending} disabled={!name.trim() || saveMutation.isPending}>Сохранить</Button>
            </div>
          </form>
        </Modal>
      ) : null}
    </section>
  );
}
