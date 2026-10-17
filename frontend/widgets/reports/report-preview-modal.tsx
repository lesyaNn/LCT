'use client';

import { useState } from 'react';
import Filter from '@atomaro/icons/24/action/Filter';
import StatisticsBoard from '@atomaro/icons/24/business/StatisticsBoard';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Table from '@atomaro/icons/24/document/Table';
import { formatDateRu } from '@/shared/lib/formatters';
import { reportColumnDefinitions, reportFiltersPayload, type ReportPreview, type ReportRequest, type ReportStatistics } from '@/shared/lib/reports-repository';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner } from '@/shared/ui/rtk/form-field';
import { MetricCard } from '@/shared/ui/rtk/metric-card';
import { Modal } from '@/shared/ui/rtk/modal';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { ReportPreviewTable } from './report-preview';
import { ReportStatisticsPanel } from './report-statistics';
import styles from './reports-page.module.css';

const reportTitle = 'Аналитический отчёт по взаимодействию с ВУЗами';
const formatCount = (value: number) => new Intl.NumberFormat('ru-RU').format(value);
const filterLabels: Record<string, string> = { university_ids: 'ВУЗы', direction_ids: 'Направления', program_ids: 'Программы', product_ids: 'Продукты', responsible_ids: 'Ответственные', workflow_statuses: 'Статусы' };

function filterSummary(request: ReportRequest): string {
  const parts = Object.entries(reportFiltersPayload(request)).filter(([key, value]) => key !== 'date_from' && key !== 'date_to' && Array.isArray(value) && value.length).map(([key, value]) => `${filterLabels[key]}: ${(value as string[]).length}`);
  return parts.length ? parts.join(' · ') : 'Не применены';
}

interface Props {
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

export function ReportPreviewModal({ request, preview, previewPending, previewError, onRetryPreview, statistics, statisticsPending, statisticsError, onRetryStatistics, generating, generateError, onGenerate, onClose }: Props) {
  const [tab, setTab] = useState('report');
  const [sheet, setSheet] = useState('data');
  const spreadsheet = request.format === 'xls' || request.format === 'xlsx';
  const period = request.date_from || request.date_to ? `${request.date_from ? `с ${formatDateRu(request.date_from)}` : 'без начальной даты'} ${request.date_to ? `по ${formatDateRu(request.date_to)}` : 'без конечной даты'}` : 'Не задан';
  const documentPeriod = [request.date_from ? `с ${formatDateRu(request.date_from)}` : '', request.date_to ? `по ${formatDateRu(request.date_to)}` : ''].filter(Boolean).join(' ') || 'не задан';
  const columns = request.columns.map((id) => reportColumnDefinitions.find((column) => column.id === id)?.label ?? id);
  const filters = reportFiltersPayload(request);
  const selectedFilters = filterSummary(request);
  // The statistics endpoint counts license rows; the selected columns can
  // produce a different row grain. Suppress such distributions below.
  const sameRowGrain = Boolean(statistics && preview && statistics.rowCount === preview.total);
  const dataTable = <ReportPreviewTable preview={preview} pending={previewPending} error={previewError} onRetry={onRetryPreview} />;

  return <Modal title="Предпросмотр отчёта" size="xl" onClose={onClose}><div className={styles.previewModal}>
    <div className={styles.previewParameters} aria-label="Выбранные параметры">
      <div className={styles.previewParameter}><Calendar size={18} fill="currentColor" aria-hidden="true" /><span><small>Период</small><strong>{period}</strong></span></div>
      <div className={styles.previewParameter}><Filter size={18} fill="currentColor" aria-hidden="true" /><span><small>Фильтры</small><strong>{selectedFilters}</strong></span></div>
      <div className={styles.previewParameter}><DocumentText size={18} fill="currentColor" aria-hidden="true" /><span><small>Состав · {request.format.toUpperCase()}</small><strong title={columns.join(', ')}>{columns.length} колонок: {columns.join(' · ')}</strong></span></div>
    </div>
    <div className={styles.previewTabs}><Tabs items={[{ id: 'report', label: 'Отчёт' }, { id: 'statistics', label: 'Статистика' }]} activeId={tab} onChange={setTab} label="Разделы предпросмотра" prefix="report-preview" /></div>
    <div className={styles.previewTabContent} role="tabpanel" aria-labelledby={`report-preview-${tab}`}>
      {tab === 'report' ? <>
        {spreadsheet ? <div className={styles.previewSheetTabs}><Tabs items={[{ id: 'data', label: 'Отчёт' }, { id: 'filters', label: 'Фильтры' }]} activeId={sheet} onChange={setSheet} label="Листы книги" prefix="report-preview-sheet" /></div> : null}
        {spreadsheet && sheet === 'filters' ? <article className={styles.previewDocument} aria-label="Лист Фильтры"><div className={styles.previewDocumentTop}><span>Лист 2 / 2 · {request.format.toUpperCase()}</span><strong>Фильтры</strong></div><div className={styles.previewDocumentBody}><p>Точные параметры запроса. Пустое значение означает, что ограничение не задано.</p><div className={styles.previewScroll} role="region" aria-label="Параметры листа Фильтры" tabIndex={0}><table><thead><tr><th scope="col">Параметр</th><th scope="col">Значение</th></tr></thead><tbody>{Object.entries(filters).map(([key, value]) => <tr key={key}><td>{key}</td><td>{Array.isArray(value) ? value.join(', ') : value ?? ''}</td></tr>)}</tbody></table></div></div></article> : <article className={styles.previewDocument} aria-label={`Содержимое ${request.format.toUpperCase()} отчёта`}>
          <div className={styles.previewDocumentTop}><span>{spreadsheet ? `Лист 1 / 2 · ${request.format.toUpperCase()}` : request.format.toUpperCase()}</span><strong>{spreadsheet ? 'Отчёт' : 'Представление файла'}</strong></div>
          <div className={styles.previewDocumentBody}><h3>{reportTitle}</h3>
            {request.format === 'json' ? <>
              <p>JSON содержит блоки metadata, filters, columns, rows и totals в этом порядке. Время формирования и автор появятся после создания файла.</p>
              <section className={styles.previewDocumentSection}><h4>metadata</h4><p>report_name: {reportTitle} · version: 1.0 · generator: CRM ИТ-Школа Ростелеком</p></section>
              <section className={styles.previewDocumentSection}><h4>filters</h4><pre>{JSON.stringify(filters, null, 2)}</pre></section>
              <section className={styles.previewDocumentSection}><h4>columns</h4><pre>{JSON.stringify(request.columns.map((key, index) => ({ key, title: columns[index] })), null, 2)}</pre></section>
              <section className={styles.previewDocumentSection}><h4>rows</h4>{preview ? <><p>Первые {formatCount(preview.rows.length)} из {formatCount(preview.total)} строк</p><pre>{JSON.stringify(preview.rows, null, 2)}</pre></> : dataTable}</section>
              {preview ? <section className={styles.previewDocumentSection}><h4>totals</h4><p>row_count: {formatCount(preview.total)} · universities: {request.columns.includes('university') ? statistics ? formatCount(statistics.universityCount) : 'рассчитывается' : 'null'}</p></section> : null}
            </> : <>
              <div className={styles.previewDocumentMetadata}><span>Период: {documentPeriod}</span><span>Фильтры: {selectedFilters === 'Не применены' ? 'не применены' : `${selectedFilters} (названия будут указаны в файле)`}</span><span>Сформирован: дата и время появятся при создании файла</span></div>
              {request.format === 'pdf' ? <section className={styles.previewDocumentSection}><h4>Ключевые показатели</h4><div className={styles.previewPdfKpis}><span>Количество ВУЗов: {statistics ? formatCount(statistics.universityCount) : 'рассчитывается'}</span><span>Количество строк (лицензий): {preview ? formatCount(preview.total) : 'рассчитывается'}</span><span>Средний прогресс workflow, %: рассчитывается при формировании</span><span>Просроченные задачи: рассчитываются при формировании</span></div></section> : null}
              <section className={styles.previewDocumentSection}><h4>{request.format === 'pdf' ? 'Данные' : 'Строки отчёта'}</h4>{dataTable}</section>
              {request.format === 'pdf' ? <section className={styles.previewDocumentSection}><h4>Графики</h4><p>Графики прогресса и выбранных измерений строятся в PDF при формировании из полного набора строк. Их точное изображение здесь недоступно.</p></section> : null}
            </>}
          </div>
        </article>}
      </> : <div className={styles.previewAnalytics}>
        <div className={styles.previewAnalyticsIntro}><div><span className={styles.previewEyebrow}>Аналитика выборки</span><h3>Что показывают данные</h3><p>{preview ? preview.total ? `В отчёт войдут ${formatCount(preview.total)} строк по выбранным условиям${statistics ? `; охвачено ${formatCount(statistics.universityCount)} вузов` : ''}. Ниже — распределения из полной выборки.` : 'По выбранным условиям строк для отчёта нет.' : 'Загружаем данные отчёта…'}</p></div><StatisticsBoard size={32} fill="currentColor" aria-hidden="true" /></div>
        <div className={styles.previewKpis}><MetricCard compact icon={Table} label="Строк в отчёте" value={preview ? formatCount(preview.total) : previewPending ? '…' : '—'} /><MetricCard compact icon={DocumentText} label="Вузов в выборке" value={statistics ? formatCount(statistics.universityCount) : statisticsPending ? '…' : '—'} /><MetricCard compact icon={Filter} label="Выбрано колонок" value={formatCount(request.columns.length)} /></div>
        <div className={styles.previewAnalyticsCharts}><div className={styles.previewSectionHeading}><h3>Распределения по выбранным полям</h3><p>Графики используют тот же фильтр и показывают только измерения с подходящей детализацией.</p></div><ReportStatisticsPanel statistics={statistics} pending={statisticsPending} error={statisticsError} sameRowGrain={sameRowGrain} onRetry={onRetryStatistics} /></div>
      </div>}
    </div>
    <div className={styles.previewModalActions}>{generateError ? <FormErrorBanner>{generateError}</FormErrorBanner> : null}<Button type="button" variant="secondary" size="m" onClick={onClose}>Закрыть</Button><Button type="button" variant="primary" size="m" loading={generating} disabled={generating || previewPending || Boolean(previewError) || !preview} onClick={onGenerate}>Сформировать отчёт</Button></div>
  </div></Modal>;
}
