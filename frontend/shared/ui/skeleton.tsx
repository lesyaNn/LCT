import type { CSSProperties } from 'react';
import styles from './skeleton.module.css';

type SkeletonDimension = number | string;
type SkeletonVariant = 'text' | 'circular' | 'rectangular';

function dimension(value: SkeletonDimension | undefined): string | undefined {
  return typeof value === 'number' ? `${value}px` : value;
}

export function Skeleton({
  variant = 'rectangular',
  width = '100%',
  height,
  className = '',
  style,
}: {
  variant?: SkeletonVariant;
  width?: SkeletonDimension;
  height?: SkeletonDimension;
  className?: string;
  style?: CSSProperties;
}) {
  const fallbackHeight = variant === 'text' ? 14 : variant === 'circular' ? width : 80;
  return <span aria-hidden="true" className={`${styles.block} ${styles[variant]} ${className}`} style={{ width: dimension(width), height: dimension(height ?? fallbackHeight), ...style }} />;
}

export function SkeletonGroup({ label = 'Загрузка данных', children, className = '' }: Readonly<{ label?: string; children: React.ReactNode; className?: string }>) {
  return <div className={`${styles.group} ${className}`} aria-busy="true" role="status"><span className={styles.visuallyHidden}>{label}</span>{children}</div>;
}

export function TextSkeleton({ lines = 3, widths }: { lines?: number; widths?: SkeletonDimension[] }) {
  return <div className={styles.textStack} aria-hidden="true">{Array.from({ length: lines }, (_, index) => <Skeleton variant="text" width={widths?.[index] ?? (index === lines - 1 ? '68%' : '100%')} key={index} />)}</div>;
}

export function MetricCardSkeleton({ count = 1 }: { count?: number }) {
  return <div className={styles.metricGrid} aria-hidden="true">{Array.from({ length: count }, (_, index) => <div className={styles.metricCard} key={index}><div className={styles.metricTop}><Skeleton variant="circular" width={36} /><Skeleton variant="text" width="52%" /></div><Skeleton variant="text" width="42%" height={30} /><Skeleton variant="text" width="70%" /></div>)}</div>;
}

export function ListSkeleton({ items = 4, withAvatar = true }: { items?: number; withAvatar?: boolean }) {
  return <div className={styles.list} aria-hidden="true">{Array.from({ length: items }, (_, index) => <div className={styles.listItem} key={index}>{withAvatar ? <Skeleton variant="circular" width={40} /> : null}<TextSkeleton lines={2} widths={['72%', '46%']} /></div>)}</div>;
}

export function TableSkeleton({ rows = 6, columns = 6, label = 'Загрузка таблицы' }: { rows?: number; columns?: number; label?: string }) {
  const gridStyle = { '--skeleton-columns': columns } as CSSProperties;
  return (
    <SkeletonGroup label={label}>
      <div className={styles.table}>
        <div className={styles.tableDesktop}>
          <div className={`${styles.tableRow} ${styles.tableHeader}`} style={gridStyle}>{Array.from({ length: columns }, (_, cell) => <span className={styles.tableCell} key={cell}><Skeleton variant="text" width={cell % 2 ? '64%' : '78%'} /></span>)}</div>
          {Array.from({ length: rows }, (_, row) => <div className={styles.tableRow} style={gridStyle} key={row}>{Array.from({ length: columns }, (_, cell) => <span className={styles.tableCell} key={cell}><Skeleton variant="text" width={`${48 + ((row + cell) % 4) * 12}%`} /></span>)}</div>)}
        </div>
        <div className={styles.tableMobile}>{Array.from({ length: Math.min(rows, 4) }, (_, row) => <div className={styles.tableMobileCard} key={row}><Skeleton variant="text" width="82%" height={18} /><TextSkeleton lines={3} widths={['58%', '74%', '46%']} /></div>)}</div>
      </div>
    </SkeletonGroup>
  );
}

export function FormSkeleton({ fields = 6 }: { fields?: number }) {
  return <SkeletonGroup label="Загрузка формы"><div className={styles.form} aria-hidden="true">{Array.from({ length: fields }, (_, index) => <div className={`${styles.formField} ${index === fields - 1 ? styles.formFieldWide : ''}`} key={index}><Skeleton variant="text" width="42%" /><Skeleton height={44} /></div>)}</div></SkeletonGroup>;
}

export function ChartSkeleton({ label = 'Загрузка графика' }: { label?: string }) {
  const heights = ['58%', '82%', '46%', '70%', '92%', '64%'];
  return <SkeletonGroup label={label}><div className={styles.chart} aria-hidden="true"><Skeleton variant="text" width="48%" height={20} /><Skeleton variant="text" width="72%" /><div className={styles.chartPlot}>{heights.map((height, index) => <Skeleton className={styles.chartBar} width="auto" height={height} key={index} />)}</div></div></SkeletonGroup>;
}
