'use client';

import { DateRangeField } from '@/shared/ui/rtk/date-range-field';
import { ActiveFilters, type ActiveFilterItem } from '@/shared/ui/rtk/active-filters';
import type { ReportFormSchema } from './report-form-schema';

type PeriodValues = Pick<ReportFormSchema, 'dateFrom' | 'dateTo'>;

interface ReportFilterFieldsProps {
  values: PeriodValues;
  errors: { dateFrom?: { message?: string }; dateTo?: { message?: string } };
  onPeriodChange: (dateFrom: string, dateTo: string) => void;
  onReset: () => void;
  activeFilters: ActiveFilterItem[];
}

/**
 * The report is built over the whole registry, so the only selector here is
 * the period. Selecting individual universities / directions / products /
 * responsibles was removed on purpose: it is a multi-step hunt for a report
 * whose default answer is "all of it", and an empty selection is exactly the
 * intended state rather than a missing value.
 *
 * The backend still supports the entity filters (they are part of the
 * UnifiedFilter contract and used by the API), they are just not exposed on
 * this page.
 */
export function ReportFilterFields({
  values,
  errors,
  onPeriodChange,
  onReset,
  activeFilters,
}: ReportFilterFieldsProps) {
  return (
    <>
      <DateRangeField
        label="Быстрые периоды и даты"
        presets
        from={values.dateFrom}
        to={values.dateTo}
        onFromChange={(dateFrom) => onPeriodChange(dateFrom, values.dateTo)}
        onToChange={(dateTo) => onPeriodChange(values.dateFrom, dateTo)}
        onRangeChange={onPeriodChange}
        fromError={errors.dateFrom?.message}
        toError={errors.dateTo?.message}
      />
      <ActiveFilters items={activeFilters} onClearAll={onReset} />
    </>
  );
}

/** Chip describing the chosen period, if any. */
export function buildActiveFilters(
  values: PeriodValues,
  onPeriodChange: (dateFrom: string, dateTo: string) => void,
): ActiveFilterItem[] {
  if (!values.dateFrom && !values.dateTo) return [];
  return [
    {
      id: 'period',
      label: `Период: ${values.dateFrom || '…'} — ${values.dateTo || '…'}`,
      onRemove: () => onPeriodChange('', ''),
    },
  ];
}
