'use client';

import { DateRangeField } from '@/shared/ui/rtk/date-range-field';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import type { ActiveFilterItem } from '@/shared/ui/rtk/active-filters';
import type { CatalogReferenceData, CatalogReferenceOption } from '@/shared/lib/catalogs-repository';
import { workflowStageStatusSemantics } from '@/shared/lib/status-semantics';
import type { ReportFormSchema } from './report-form-schema';

export type ReportFilterKey = 'universityIds' | 'directionIds' | 'programIds' | 'productIds' | 'responsibleIds' | 'workflowStatuses';
type FilterOptions = Pick<CatalogReferenceData, 'universities' | 'directions' | 'programs' | 'products' | 'responsibles'>;

const fields: Array<{ key: ReportFilterKey; label: string; source: keyof FilterOptions }> = [
  { key: 'universityIds', label: 'ВУЗы', source: 'universities' },
  { key: 'directionIds', label: 'ИТ-направления', source: 'directions' },
  { key: 'programIds', label: 'ИТ-программы', source: 'programs' },
  { key: 'productIds', label: 'ИТ-продукты', source: 'products' },
  { key: 'responsibleIds', label: 'Ответственные', source: 'responsibles' },
];

const statusOptions = Object.entries(workflowStageStatusSemantics).map(([id, item]) => ({ id, name: item.label }));

function availableOptions(key: ReportFilterKey, values: ReportFormSchema, options: FilterOptions): CatalogReferenceOption[] {
  if (key === 'programIds' && values.directionIds.length) {
    return options.programs.filter((item) => !item.parentId || values.directionIds.includes(item.parentId));
  }
  if (key === 'productIds' && (values.directionIds.length || values.programIds.length)) {
    const programs = values.programIds.length
      ? values.programIds
      : options.programs.filter((item) => !item.parentId || values.directionIds.includes(item.parentId)).map((item) => item.id);
    return options.products.filter((item) => !item.parentId || programs.includes(item.parentId));
  }
  return options[key === 'universityIds' ? 'universities' : key === 'directionIds' ? 'directions' : key === 'programIds' ? 'programs' : key === 'productIds' ? 'products' : 'responsibles'];
}

interface ReportFilterFieldsProps {
  values: ReportFormSchema;
  options?: FilterOptions;
  loading: boolean;
  unavailable: boolean;
  errors: { dateFrom?: { message?: string }; dateTo?: { message?: string } };
  onChange: (key: ReportFilterKey, values: string[]) => void;
  onPeriodChange: (dateFrom: string, dateTo: string) => void;
  onReset: () => void;
}

export function ReportFilterFields({ values, options, loading, unavailable, errors, onChange, onPeriodChange, onReset }: ReportFilterFieldsProps) {
  const activeFilters = buildActiveFilters(values, options, onChange, onPeriodChange);
  return <FilterToolbar
    label="Фильтры отчёта"
    collapsible
    controls={() => <>
      {fields.map(({ key, label }) => <MultiSelect key={key} label={label} labelPlacement="outside" options={options ? availableOptions(key, values, options) : []} values={values[key]} onChange={(selected) => onChange(key, selected)} searchable loading={loading} disabled={unavailable} />)}
      <MultiSelect label="Статусы этапов" labelPlacement="outside" options={statusOptions} values={values.workflowStatuses} onChange={(selected) => onChange('workflowStatuses', selected)} searchable />
    </>}
    periodControls={<DateRangeField
      label="Период взаимодействия"
      presets
      wideSplit
      from={values.dateFrom}
      to={values.dateTo}
      onFromChange={(dateFrom) => onPeriodChange(dateFrom, values.dateTo)}
      onToChange={(dateTo) => onPeriodChange(values.dateFrom, dateTo)}
      onRangeChange={onPeriodChange}
      fromError={errors.dateFrom?.message}
      toError={errors.dateTo?.message}
    />}
    onReset={onReset}
    resetDisabled={!activeFilters.length}
    mobileCount={activeFilters.length}
    activeFilters={activeFilters}
  />;
}

function selectedNames(ids: string[], options: CatalogReferenceOption[]): string {
  const names = ids.map((id) => options.find((item) => item.id === id)?.name ?? id);
  return names.length > 2 ? `${names.slice(0, 2).join(', ')} +${names.length - 2}` : names.join(', ');
}

export function buildActiveFilters(values: ReportFormSchema, options: FilterOptions | undefined, onChange: (key: ReportFilterKey, values: string[]) => void, onPeriodChange: (dateFrom: string, dateTo: string) => void): ActiveFilterItem[] {
  const chips: ActiveFilterItem[] = [];
  if (values.dateFrom || values.dateTo) chips.push({ id: 'period', label: `Период: ${values.dateFrom || '…'} — ${values.dateTo || '…'}`, onRemove: () => onPeriodChange('', '') });
  for (const { key, label, source } of fields) {
    if (values[key].length) chips.push({ id: key, label: `${label}: ${selectedNames(values[key], options?.[source] ?? [])}`, onRemove: () => onChange(key, []) });
  }
  if (values.workflowStatuses.length) chips.push({ id: 'workflowStatuses', label: `Статусы: ${selectedNames(values.workflowStatuses, statusOptions)}`, onRemove: () => onChange('workflowStatuses', []) });
  return chips;
}
