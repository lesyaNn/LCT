'use client';

import { Controller, type Control } from 'react-hook-form';
import { Button } from '@/shared/ui/rtk/button';
import { FormError } from '@/shared/ui/rtk/form-field';
import {
  reportColumnDefinitions,
  reportColumnPresetNames,
  reportColumnPresets,
  TZ_REPORT_COLUMNS,
} from '@/shared/lib/reports-repository';
import type { ReportFormSchema } from './report-form-schema';
import styles from './reports-page.module.css';

interface ReportColumnSelectorProps {
  control: Control<ReportFormSchema>;
  error?: string;
}

/**
 * Column picker.
 *
 * The first block is the 5 ТЗ columns and the second one is the extra
 * supported columns, so the required set is visibly distinct from the
 * optional one instead of appearing as an undifferentiated list of 17.
 */
export function ReportColumnSelector({ control, error }: ReportColumnSelectorProps) {
  return (
    <div className={styles.columnSection}>
      <div className={styles.sectionHeading}>
        <div>
          <h3>Колонки</h3>
          <p>Выберите данные, которые войдут в отчёт.</p>
        </div>
        {error ? <FormError id="report-columns-error">{error}</FormError> : null}
      </div>
      <Controller
        control={control}
        name="columnIds"
        render={({ field }) => {
          const toggle = (id: string) =>
            field.onChange(
              field.value.includes(id)
                ? field.value.filter((value) => value !== id)
                : [...field.value, id],
            );
          return (
            <>
              <div className={styles.columnPresets} aria-label="Наборы колонок">
                {reportColumnPresetNames.map((name) => (
                  <Button key={name} variant="ghost" size="s" type="button" onClick={() => field.onChange([...reportColumnPresets[name]])}>
                    {name}
                  </Button>
                ))}
              </div>
              <fieldset className={styles.columnFieldset}>
                <legend className={styles.columnLegend}>Колонки по ТЗ</legend>
                <div className={styles.columnGrid}>
                  {reportColumnDefinitions
                    .filter((column) => (TZ_REPORT_COLUMNS as readonly string[]).includes(column.id))
                    .map((column) => (
                      <label key={column.id}>
                        <input type="checkbox" checked={field.value.includes(column.id)} onChange={() => toggle(column.id)} />
                        <span>{column.label}</span>
                      </label>
                    ))}
                </div>
              </fieldset>
              <fieldset className={styles.columnFieldset}>
                <legend className={styles.columnLegend}>Дополнительные колонки</legend>
                <div className={styles.columnGrid}>
                  {reportColumnDefinitions
                    .filter((column) => !(TZ_REPORT_COLUMNS as readonly string[]).includes(column.id))
                    .map((column) => (
                      <label key={column.id}>
                        <input type="checkbox" checked={field.value.includes(column.id)} onChange={() => toggle(column.id)} />
                        <span>{column.label}</span>
                      </label>
                    ))}
                </div>
              </fieldset>
            </>
          );
        }}
      />
    </div>
  );
}
