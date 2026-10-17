'use client';

import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import { EmptyState } from '@/shared/ui/empty-state';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { TableSkeleton } from '@/shared/ui/skeleton';
import {
  reportColumnDefinitions,
  type ReportPreview,
} from '@/shared/lib/reports-repository';
import styles from './reports-page.module.css';

const columnLabel = (id: string) =>
  reportColumnDefinitions.find((column) => column.id === id)?.label ?? id;

/** A value as it arrives from the API, rendered without guessing a format. */
function renderCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'boolean') return value ? '1' : '0';
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return `${value.slice(8, 10)}.${value.slice(5, 7)}.${value.slice(0, 4)}`;
  return String(value);
}

interface ReportPreviewTableProps {
  preview?: ReportPreview;
  pending: boolean;
  error: unknown;
  onRetry: () => void;
}

/**
 * Live view of the current selection (ТЗ step 8: "увидеть актуальную выборку").
 *
 * The table shows at most `previewLimit` rows while `total` is the real
 * export size, so the user can tell that the report is larger than the page
 * they are looking at. The export itself is never built from these rows.
 */
export function ReportPreviewTable({ preview, pending, error, onRetry }: ReportPreviewTableProps) {
  if (error) {
    return (
      <EmptyState
        title="Не удалось получить предпросмотр"
        description="Проверьте параметры выборки и повторите попытку."
        headingLevel={3}
        primaryAction={{ label: 'Повторить', onClick: onRetry }}
      />
    );
  }

  if (pending && !preview) return <TableSkeleton rows={5} columns={5} label="Загрузка предпросмотра" />;
  if (preview && !preview.rows.length) {
    return (
      <EmptyState
        title="По выбранным параметрам ничего не найдено"
        description="Измените период и откройте предпросмотр снова."
        headingLevel={3}
      />
    );
  }

  if (!preview) return null;

  const shown = preview.rows.length;
  const truncated = preview.total > shown;

  return (
    <div className={styles.previewSurface}>
      <div className={styles.previewTableMeta}>
        <p>
          {truncated
            ? `Показаны первые ${shown} из ${preview.total} строк. В файл попадут все ${preview.total}.`
            : `Всего строк: ${preview.total}.`}
        </p>
        {pending ? <span className={styles.previewRefreshing}>Обновляем…</span> : null}
      </div>
      {truncated ? (
        <p className={styles.previewNotice}>
          <InformationStroke size={16} fill="currentColor" aria-hidden="true" />
          Показано начало файла. Остальные {preview.total - shown} строк будут в сформированном отчёте.
        </p>
      ) : null}
      <TableShell ariaLabel="Предпросмотр отчёта" className={styles.previewTableShell}>
        <div className={styles.previewScroll}>
          <table>
            <caption className={styles.visuallyHidden}>Первые строки отчёта по текущим параметрам</caption>
            <thead>
              <tr>
                {preview.columns.map((column) => (
                  <th scope="col" key={column}>{columnLabel(column)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((row, index) => (
                <tr key={index} data-testid={`report-preview-row-${index}`}>
                  {preview.columns.map((column) => (
                    <td key={column}>{renderCell(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </TableShell>
    </div>
  );
}
