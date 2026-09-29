import { z } from 'zod';
import { REPORT_FORMATS, type ReportFormValues } from '@/shared/lib/reports-repository';
import { optionalDateField } from '@/shared/lib/form-validation';

/**
 * Form validation for the report parameters.
 *
 * The format list is derived from `REPORT_FORMATS` so adding a backend format
 * cannot leave the form schema out of sync (which previously made the zod
 * union and the `ReportFormat` type drift apart).
 */
const formatIds = REPORT_FORMATS.map((format) => format.id) as [
  ReportFormValues['format'],
  ...ReportFormValues['format'][],
];

export const reportSchema = z
  // The report covers the whole registry: the only data selector is the
  // period. Entity filters stay in the UnifiedFilter contract (and the API)
  // but are not part of this form.
  .object({
    dateFrom: optionalDateField,
    dateTo: optionalDateField,
    columnIds: z.array(z.string()).min(1, 'Выберите хотя бы одну колонку.'),
    format: z.enum(formatIds),
  })
  .superRefine((values, context) => {
    if (values.dateFrom && values.dateTo && values.dateFrom > values.dateTo) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['dateTo'],
        message: 'Дата окончания не может быть раньше даты начала.',
      });
    }
  });

export type ReportFormSchema = z.infer<typeof reportSchema>;

/** Form fields the backend may report errors against. */
export const reportFields = ['dateFrom', 'dateTo', 'columnIds', 'format'] as const;
