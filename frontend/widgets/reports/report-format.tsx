'use client';

import DocumentText from '@atomaro/icons/24/document/DocumentText';
import { Controller, type Control } from 'react-hook-form';
import { REPORT_FORMATS, REPORTS_API_CAPABILITIES } from '@/shared/lib/reports-repository';
import type { ReportFormSchema } from './report-form-schema';
import styles from './reports-page.module.css';

/** Human-readable notes about the legacy XLS limits (BIFF8). */
const FORMAT_HINTS: Record<string, string> = {
  xls: 'Старый формат Excel, до 65 536 строк.',
  xlsx: 'Рекомендуемый формат Excel.',
  pdf: 'Готов к печати, кириллица поддерживается.',
  json: 'Для выгрузки в другие системы.',
};

interface ReportFormatFieldProps {
  control: Control<ReportFormSchema>;
}

/** Export format picker, driven by the backend capability flags. */
export function ReportFormatField({ control }: ReportFormatFieldProps) {
  return (
    <section className={styles.formSection} aria-labelledby="report-format-heading">
      <div className={styles.sectionHeading}>
        <div className={styles.headingWithIcon}>
          <DocumentText size={18} fill="currentColor" aria-hidden="true" />
          <div>
            <h3 id="report-format-heading">Формат</h3>
            <p>Выберите формат файла отчёта.</p>
          </div>
        </div>
      </div>
      <Controller
        control={control}
        name="format"
        render={({ field }) => (
          <fieldset className={styles.radioGroup}>
            <legend className={styles.visuallyHidden}>Формат отчёта</legend>
            {REPORT_FORMATS.map((format) => {
              const available = REPORTS_API_CAPABILITIES.formats[format.id];
              return (
                <label key={format.id} className={!available ? styles.optionDisabled : undefined}>
                  <input
                    type="radio"
                    value={format.id}
                    checked={field.value === format.id}
                    disabled={!available}
                    onChange={() => field.onChange(format.id)}
                  />
                  {format.label}
                  {FORMAT_HINTS[format.id] ? <small>{FORMAT_HINTS[format.id]}</small> : null}
                  {!available ? <small>недоступно</small> : null}
                </label>
              );
            })}
          </fieldset>
        )}
      />
    </section>
  );
}
