'use client';

import { useState } from 'react';
import { formatDateRu } from '@/shared/lib/formatters';
import {
  reportColumnDefinitions,
  reportFiltersPayload,
  type ReportPreview,
  type ReportRequest,
  type ReportStatistics,
} from '@/shared/lib/reports-repository';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { MetricCard } from '@/shared/ui/rtk/metric-card';
import { Modal } from '@/shared/ui/rtk/modal';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { ReportPreviewTable } from './report-preview';
import { ReportStatisticsPanel } from './report-statistics';
import styles from './reports-page.module.css';

const numberFormatter = new Intl.NumberFormat('ru-RU');

function countWord(count: number, forms: [string, string, string]): string {
  const lastTwo = count % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return forms[2];
  const last = count % 10;
  return last === 1 ? forms[0] : last >= 2 && last <= 4 ? forms[1] : forms[2];
}

interface ReportPreviewModalProps {
  request: ReportRequest;
  preview?: ReportPreview;
  previewPending: boolean;
  previewError: unknown;
  onRetryPreview: () => void;
  statistics?: ReportStatistics;
  statisticsPending: boolean;
  statisticsError: unknown;
  onRetryStatistics: () => void;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
  onClose: () => void;
}

export function ReportPreviewModal({
  request, preview, previewPending, previewError, onRetryPreview,
  statistics, statisticsPending, statisticsError, onRetryStatistics,
  generating, generateError, onGenerate, onClose,
}: ReportPreviewModalProps) {
  const [sheet, setSheet] = useState('data');
  const spreadsheet = request.format === 'xls' || request.format === 'xlsx';
  const period = request.date_from || request.date_to
    ? `${request.date_from ? `с ${formatDateRu(request.date_from)}` : 'без начальной даты'} · ${request.date_to ? `по ${formatDateRu(request.date_to)}` : 'без конечной даты'}`
    : 'За всё время';
  const selectedColumns = request.columns.map((id) => reportColumnDefinitions.find((column) => column.id === id)?.label ?? id);
  // Preview.universityCount counts only the bounded page. Statistics has the
  // full distinct-university count; its row slices use license grain.
  const sameRowGrain = Boolean(statistics && preview && statistics.rowCount === preview.total);

  return (
    <Modal title="Предпросмотр отчёта" size="l" onClose={onClose}>
      <div className={styles.previewModal}>
        <div className={styles.previewModalMeta} aria-label="Параметры отчёта">
          <span><small>Период</small><strong>{period}</strong></span>
          <span><small>Фильтры</small><strong>Все доступные вузы</strong></span>
          <span><small>Формат</small><strong>{request.format.toUpperCase()}</strong></span>
        </div>
        <p className={styles.previewModalColumns} title={selectedColumns.join(', ')}>
          <strong>Состав:</strong> {selectedColumns.join(' · ')}
        </p>

        {previewError || !preview ? (
          <section className={styles.previewModalSection} aria-label="Данные отчёта">
            <ReportPreviewTable preview={preview} pending={previewPending} error={previewError} onRetry={onRetryPreview} />
          </section>
        ) : (
          <>
            <section className={styles.previewModalSection} aria-labelledby="report-preview-summary">
              <h3 id="report-preview-summary">Краткие итоги</h3>
              <p className={styles.previewSummary}>
                {preview.total
                  ? `В отчёте будет ${numberFormatter.format(preview.total)} ${countWord(preview.total, ['строка', 'строки', 'строк'])}${statistics ? ` по ${numberFormatter.format(statistics.universityCount)} ${countWord(statistics.universityCount, ['вузу', 'вузам', 'вузам'])}` : ''}.`
                  : 'По выбранным условиям строк для отчёта нет.'}
              </p>
              <div className={styles.previewKpis}>
                <MetricCard compact centered label="Строк в отчёте" value={numberFormatter.format(preview.total)} />
                <MetricCard compact centered label="Вузов в выборке" value={statistics ? numberFormatter.format(statistics.universityCount) : statisticsPending ? '…' : '—'} />
                <MetricCard compact centered label="Колонок" value={numberFormatter.format(preview.columns.length)} />
              </div>
            </section>

            {preview.total > 0 ? (
              <section className={styles.previewModalSection} aria-labelledby="report-preview-analytics">
                <div className={styles.previewSectionHeading}>
                  <h3 id="report-preview-analytics">Аналитика по выборке</h3>
                  <p>Графики помогают оценить данные; ниже показано содержимое файла.</p>
                </div>
                <ReportStatisticsPanel statistics={statistics} pending={statisticsPending} error={statisticsError} sameRowGrain={sameRowGrain} onRetry={onRetryStatistics} />
              </section>
            ) : null}

            <section className={styles.previewModalSection} aria-labelledby="report-preview-file">
              <div className={styles.previewSectionHeading}>
                <h3 id="report-preview-file">Что попадёт в файл</h3>
                <p>Столбцы и первые строки по тем же параметрам, что и формируемый отчёт.</p>
              </div>
              {spreadsheet ? (
                <Tabs
                  items={[{ id: 'data', label: 'Отчёт' }, { id: 'filters', label: 'Фильтры' }]}
                  activeId={sheet}
                  onChange={setSheet}
                  label="Листы файла отчёта"
                  prefix="report-preview-sheet"
                />
              ) : null}
              {sheet === 'filters' && spreadsheet ? (
                <div className={styles.previewSurface}>
                  <p className={styles.previewFilterHint}>Пустое значение означает, что ограничение не задано.</p>
                  <TableShell ariaLabel="Лист фильтров отчёта">
                    <div className={styles.previewScroll}>
                      <table>
                        <thead><tr><th scope="col">Параметр</th><th scope="col">Значение</th></tr></thead>
                        <tbody>
                          {Object.entries(reportFiltersPayload(request)).map(([key, value]) => (
                            <tr key={key}><td>{key}</td><td>{Array.isArray(value) ? value.join(', ') : value ?? ''}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </TableShell>
                </div>
              ) : (
                <ReportPreviewTable preview={preview} pending={false} error={null} onRetry={onRetryPreview} />
              )}
            </section>
          </>
        )}

        <div className={styles.previewModalActions}>
          {generateError ? <FormErrorBanner>{generateError}</FormErrorBanner> : null}
          <Button type="button" variant="secondary" size="m" onClick={onClose}>Закрыть</Button>
          <Button type="button" variant="primary" size="m" loading={generating} disabled={generating || previewPending || Boolean(previewError) || !preview} onClick={onGenerate}>
            Сформировать отчёт
          </Button>
        </div>
      </div>
    </Modal>
  );
}
