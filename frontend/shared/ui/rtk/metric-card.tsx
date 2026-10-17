import type { ComponentType, ReactNode } from 'react';
import { StatusBadge } from './status-badge';
import styles from './metric-card.module.css';

type IndicatorIntent = 'success' | 'warning' | 'danger';

interface MetricIndicator {
  value: number;
  label: string;
  intent: IndicatorIntent;
}

interface MetricCardProps {
  label: string;
  value: ReactNode;
  icon?: ComponentType<{ fill?: string; size?: number }>;
  indicators?: MetricIndicator[];
  centered?: boolean;
  compact?: boolean;
}

export function MetricCard({ label, value, icon: Icon, indicators, centered = false, compact = false }: MetricCardProps) {
  return (
    <article className={`${styles.card} ${centered ? styles.centered : ''} ${compact ? styles.compact : ''}`}>
      {centered ? null : <div className={styles.header}>{Icon ? <span className={styles.icon} aria-hidden="true"><Icon size={20} fill="currentColor" /></span> : null}<h3>{label}</h3></div>}
      <strong className={styles.value}>{value}</strong>
      {centered ? <span className={styles.centeredLabel}>{label}</span> : null}
      {indicators?.length ? <div className={styles.indicators}>{indicators.map((indicator) => <StatusBadge intent={indicator.intent} variant="inline" key={indicator.label}>{indicator.value} {indicator.label}</StatusBadge>)}</div> : null}
    </article>
  );
}
