'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Input } from '@/shared/ui/rtk/form-controls';
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
}

/** Saved filter/column presets. */
export function ReportTemplatesSection({ currentValues, onApply }: ReportTemplatesSectionProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const templatesQuery = useQuery({ queryKey: reportQueryKeys.templates, queryFn: listReportTemplates, staleTime: 60_000 });
  const templates = templatesQuery.data ?? [];

  const saveMutation = useMutation({
    mutationFn: (templateName: string) => createReportTemplate(templateName, reportRequestFromForm(currentValues)),
    onSuccess: (template) => {
      queryClient.setQueryData<ReportTemplate[]>(reportQueryKeys.templates, (current = []) => [...current, template]);
      setName('');
      setError(null);
    },
    onError: (cause) => setError(normalizeApiError(cause, { fallbackMessage: 'Не удалось сохранить шаблон.' }).message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteReportTemplate,
    onSuccess: (_, templateId) => {
      queryClient.setQueryData<ReportTemplate[]>(reportQueryKeys.templates, (current = []) => current.filter((template) => template.id !== templateId));
    },
    onError: (cause) => setError(normalizeApiError(cause, { fallbackMessage: 'Не удалось удалить шаблон.' }).message),
  });

  return (
    <section className={styles.formSection} aria-labelledby="report-templates-heading">
      <div className={styles.sectionHeading}>
        <div>
          <h3 id="report-templates-heading">Шаблоны</h3>
          <p>Сохраните параметры и применяйте их повторно.</p>
        </div>
      </div>
      {templates.length ? (
        <div className={styles.columnPresets} aria-label="Сохранённые шаблоны">
          {templates.map((template) => (
            <span key={template.id}>
              <Button variant="ghost" size="s" type="button" onClick={() => onApply(template)}>
                {template.name}{template.isShared ? ' (общий)' : ''}
              </Button>
              <Button
                variant="ghost"
                size="s"
                type="button"
                aria-label={`Удалить шаблон ${template.name}`}
                onClick={() => deleteMutation.mutate(template.id)}
              >
                ✕
              </Button>
            </span>
          ))}
        </div>
      ) : (
        <p className={styles.muted}>Шаблонов пока нет.</p>
      )}
      <div className={styles.templateActions}>
        <FormField label="Название шаблона" htmlFor="report-template-name" error={error ?? undefined} errorId="report-template-name-error">
          <Input
            id="report-template-name"
            placeholder="Например, ежемесячный отчёт"
            value={name}
            onChange={(event) => { setName(event.target.value); if (error) setError(null); }}
            maxLength={256}
            disabled={saveMutation.isPending}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={error ? 'report-template-name-error' : undefined}
          />
        </FormField>
        <Button
          variant="ghost"
          size="s"
          type="button"
          loading={saveMutation.isPending}
          disabled={!name.trim() || saveMutation.isPending}
          onClick={() => void saveMutation.mutate(name.trim())}
        >
          Сохранить
        </Button>
      </div>
      {templatesQuery.isError ? (
        <FormErrorBanner>
          Не удалось загрузить шаблоны.{' '}
          <Button type="button" variant="ghost" size="s" onClick={() => void templatesQuery.refetch()}>Повторить</Button>
        </FormErrorBanner>
      ) : null}
    </section>
  );
}
