import { z } from 'zod';
import { REPORT_FORMATS, REPORT_GROUP_IDS, type ReportFormValues } from '@/shared/lib/reports-repository';
import { optionalDateField } from '@/shared/lib/form-validation';
import { workflowStageStatusSemantics } from '@/shared/lib/status-semantics';

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
const workflowStatusIds = Object.keys(workflowStageStatusSemantics) as [ReportFormValues['workflowStatuses'][number], ...ReportFormValues['workflowStatuses'][number][]];

export const reportSchema = z
  .object({
    dateFrom: optionalDateField,
    dateTo: optionalDateField,
    universityIds: z.array(z.string()),
    directionIds: z.array(z.string()),
    programIds: z.array(z.string()),
    productIds: z.array(z.string()),
    responsibleIds: z.array(z.string()),
    workflowStatuses: z.array(z.enum(workflowStatusIds)),
    groupBy: z.union([z.literal(''), z.enum(REPORT_GROUP_IDS)]),
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
export const reportFields = ['dateFrom', 'dateTo', 'universityIds', 'directionIds', 'programIds', 'productIds', 'responsibleIds', 'workflowStatuses', 'groupBy', 'columnIds', 'format'] as const;
