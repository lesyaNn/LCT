'use client';

import ChevronSort from '@atomaro/icons/24/navigation/ChevronSort';
import SortDown from '@atomaro/icons/24/editor/SortDown';
import SortUp from '@atomaro/icons/24/editor/SortUp';
import { Button } from '@/shared/ui/rtk/button';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { useMemo, useState, type ReactNode } from 'react';
import styles from './passport-data-table.module.css';

export interface PassportTableColumn<T> {
  id: string;
  label: string;
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
  render: (row: T) => ReactNode;
}

export interface PassportMobileField<T> {
  label: string;
  render: (row: T) => ReactNode;
}

interface PassportDataTableProps<T extends { id: string }> {
  rows: T[];
  columns: PassportTableColumn<T>[];
  mobileFields: PassportMobileField<T>[];
  emptyMessage: string;
  pageSize?: number;
  groupBy?: (row: T) => string;
}

type SortDirection = 'asc' | 'desc';

function compareValues(left: string | number, right: string | number): number {
  if (typeof left === 'number' && typeof right === 'number') return left - right;
  return String(left).localeCompare(String(right), 'ru', { sensitivity: 'base' });
}

function SortIcon({ direction }: { direction: SortDirection | null }) {
  if (direction === 'asc') return <SortUp size={16} fill="currentColor" />;
  if (direction === 'desc') return <SortDown size={16} fill="currentColor" />;
  return <ChevronSort size={16} fill="currentColor" />;
}

export function PassportDataTable<T extends { id: string }>({ rows, columns, mobileFields, emptyMessage, pageSize = 20, groupBy }: PassportDataTableProps<T>) {
  const [sortId, setSortId] = useState<string | null>(null);
  const [direction, setDirection] = useState<SortDirection>('asc');
  const [page, setPage] = useState(1);
  const sortableColumns = useMemo(() => columns.filter((column) => column.sortable && column.sortValue), [columns]);

  const sortedRows = useMemo(() => {
    if (!sortId) return rows;
    const column = sortableColumns.find((item) => item.id === sortId);
    if (!column?.sortValue) return rows;
    return [...rows].sort((left, right) => compareValues(column.sortValue?.(left) ?? '', column.sortValue?.(right) ?? '') * (direction === 'desc' ? -1 : 1));
  }, [direction, rows, sortId, sortableColumns]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleRows = sortedRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const visibleGroups = useMemo(() => {
    if (!groupBy) return [{ label: null, rows: visibleRows }];
    const groups = new Map<string, T[]>();
    visibleRows.forEach((row) => {
      const label = groupBy(row);
      groups.set(label, [...(groups.get(label) ?? []), row]);
    });
    return [...groups.entries()].map(([label, groupedRows]) => ({ label, rows: groupedRows }));
  }, [groupBy, visibleRows]);

  const handleSort = (column: PassportTableColumn<T>) => {
    if (!column.sortable || !column.sortValue) return;
    setPage(1);
    if (sortId === column.id) {
      setDirection((current) => current === 'asc' ? 'desc' : 'asc');
    } else {
      setSortId(column.id);
      setDirection('asc');
    }
  };

  if (!rows.length) {
    return <div className={styles.empty} role="status">{emptyMessage}</div>;
  }

  return (
    <TableShell>
      <div className={styles.desktopTableWrap}>
        <table className={`${styles.table} ${columns.length >= 7 ? styles.wideTable : ''}`}>
          <thead>
            <tr>
              {columns.map((column) => {
                const active = sortId === column.id;
                return (
                  <th key={column.id} scope="col" aria-sort={active ? direction === 'asc' ? 'ascending' : 'descending' : 'none'}>
                    {column.sortable ? (
                      <button className={styles.sortButton} type="button" onClick={() => handleSort(column)} aria-label={`${column.label}: сортировать ${active && direction === 'asc' ? 'по убыванию' : 'по возрастанию'}`}>
                        <span>{column.label}</span><SortIcon direction={active ? direction : null} />
                      </button>
                    ) : column.label}
                  </th>
                );
              })}
            </tr>
          </thead>
          {visibleGroups.map((group) => <tbody key={group.label ?? 'all'}>{group.label ? <tr className={styles.groupRow} key={`group-${group.label}`}><th colSpan={columns.length} scope="rowgroup"><span>{group.label}</span><span className={styles.groupCount}>{group.rows.length}</span></th></tr> : null}{group.rows.map((row) => <tr key={row.id}>{columns.map((column) => <td key={column.id}>{column.render(row)}</td>)}</tr>)}</tbody>)}
        </table>
      </div>
      <div className={styles.mobileCards}>
        {visibleGroups.map((group) => <div className={styles.mobileGroup} key={group.label ?? 'all'}>{group.label ? <h3 className={styles.groupHeading}>{group.label}<span className={styles.groupCount}>{group.rows.length}</span></h3> : null}{group.rows.map((row) => <article className={styles.mobileCard} key={row.id}>{mobileFields.map((field) => <div className={styles.mobileField} key={field.label}><span className={styles.mobileLabel}>{field.label}</span><div className={styles.mobileValue}>{field.render(row)}</div></div>)}</article>)}</div>)}
      </div>
      {totalPages > 1 ? (
        <div className={styles.pagination} aria-label="Пагинация таблицы">
          <span>Страница {currentPage} из {totalPages}</span>
          <div className={styles.paginationActions}>
            <Button variant="ghost" size="s" type="button" disabled={currentPage === 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Назад</Button>
            <Button variant="ghost" size="s" type="button" disabled={currentPage === totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))}>Далее</Button>
          </div>
        </div>
      ) : null}
    </TableShell>
  );
}

export function PassportTableSkeleton() {
  return <TableShell><div className={styles.tableSkeleton} aria-live="polite" aria-busy="true"><span className={styles.skeletonHeader} />{Array.from({ length: 5 }, (_, index) => <span className={styles.skeletonRow} key={index} />)}</div></TableShell>;
}
