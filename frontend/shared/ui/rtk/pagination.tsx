import { Button } from './button';
import styles from './pagination.module.css';

export const DEFAULT_PAGE_SIZE = 12;
export const PAGE_SIZE_OPTIONS = [6, 12, 24];

type PaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  label: string;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
};

export function Pagination({ page, pageSize, total, label, onPageChange, onPageSizeChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.max(1, Math.min(page, totalPages));
  const pages = Array.from({ length: Math.min(totalPages, 5) }, (_, index) => {
    if (totalPages <= 5) return index + 1;
    if (safePage <= 3) return index + 1;
    if (safePage >= totalPages - 2) return totalPages - 4 + index;
    return safePage - 2 + index;
  });
  const firstItem = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const lastItem = Math.min(safePage * pageSize, total);

  return <div className={styles.surface}>
    <nav className={styles.pagination} aria-label={label}>
      <span className={styles.summary}>{firstItem}–{lastItem} из {total}</span>
      <div className={styles.pageButtons}>
        <Button variant="secondary" size="s" type="button" disabled={safePage === 1} onClick={() => onPageChange(safePage - 1)}>Назад</Button>
        {pages.map((pageNumber) => <button className={pageNumber === safePage ? styles.pageButtonActive : styles.pageButton} type="button" aria-current={pageNumber === safePage ? 'page' : undefined} key={pageNumber} onClick={() => onPageChange(pageNumber)}>{pageNumber}</button>)}
        <Button variant="secondary" size="s" type="button" disabled={safePage === totalPages} onClick={() => onPageChange(safePage + 1)}>Далее</Button>
      </div>
      <label className={styles.pageSize}><span>На странице</span><select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>{PAGE_SIZE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
    </nav>
  </div>;
}
