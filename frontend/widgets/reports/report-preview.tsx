'use client';

import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import { EmptyState } from '@/shared/ui/empty-state';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { TableSkeleton } from '@/shared/ui/skeleton';
import {
  REPORT_PREVIEW_LIMIT,
  reportColumnDefinitions,
  type ReportPreview,
} from '@/shared/lib/reports-repository';
import styles from './reports-page.module.css';

const columnLabel = (id: string) =>
  reportColumnDefinitions.find((column) => column.id === id)?.label ?? id;

/** A value as it arrives from the API, rendered without guessing a format. */
function renderCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'да' : 'нет';
  return String(value);
}

interface ReportPreviewTableProps {
  preview?: ReportPreview;
  pending: boolean;
  error: unknown;
  /** True once the user has chosen any parameter. */
  dirty: boolean;
  onRetry: () => void;
}

/**
 * Live view of the current selection (ТЗ step 8: "увидеть актуальную выборку").
 *
 * The table shows at most `previewLimit` rows while `total` is the real
 * export size, so the user can tell that the report is larger than the page
 * they are looking at. The export itself is never built from these rows.
 */
export function ReportPreviewTable({ preview, pending, error, dirty, onRetry }: ReportPreviewTableProps) {
  const titleId = 'report-preview-heading';

  if (!dirty && !pending && !preview) {
    return (
      <EmptyState
        title="Выборка ещё не задана"
        description="Укажите период или выберите вузы, направления, продукты и ответственных — здесь появится предпросмотр."
        headingLevel={3}
      />
    );
  }

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
        description="Проверьте период взаимодействия и фильтры: вуз попадает в отчёт, если у него было хотя бы одно взаимодействие внутри периода."
        headingLevel={3}
      />
    );
  }

  if (!preview) return null;

  const shown = preview.rows.length;
  const truncated = preview.total > shown;

  return (
    <section className={styles.previewSurface} aria-labelledby={titleId}>
      <div className={styles.sectionHeading}>
        <div>
          <h3 id={titleId}>Предпросмотр выборки</h3>
          <p>
            {truncated
              ? `Показаны первые ${shown} из ${preview.total} строк. В файл попадут все ${preview.total}.`
              : `Всего строк: ${preview.total}.`}
          </p>
        </div>
        {pending ? <span className={styles.previewRefreshing}>Обновляем…</span> : null}
      </div>
      {truncated ? (
        <p className={styles.previewNotice}>
          <InformationStroke size={16} fill="currentColor" aria-hidden="true" />
          Предпросмотр ограничен {preview.previewLimit || REPORT_PREVIEW_LIMIT} строками — это ограничение только экрана, экспорт содержит всю выборку.
        </p>
      ) : null}
      <TableShell ariaLabel="Предпросмотр отчёта">
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
    </section>
  );
}
