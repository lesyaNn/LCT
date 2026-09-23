import type { ComponentType } from 'react';
import AttentionStroke from '@atomaro/icons/24/alert/AttentionStroke';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import OkStroke from '@atomaro/icons/24/alert/OkStroke';
import { readinessSemantics, type ReadinessIcon } from '@/shared/lib/status-semantics';
import type { TeacherReadiness } from '@/shared/lib/universities-repository';
import { StatusBadge } from './status-badge';
import styles from './readiness-badge.module.css';

export type ReadinessBadgeSize = 'sm' | 'md' | 'lg';

const readinessIcons: Record<ReadinessIcon, ComponentType<{ size?: number; fill?: string }>> = {
  success: OkStroke,
  warning: AttentionStroke,
  error: ErrorStroke,
};

const fallbackIcon = InformationStroke;

const readinessIconSizes: Record<ReadinessBadgeSize, number> = { sm: 14, md: 16, lg: 18 };

export interface ReadinessBadgeProps {
  readiness: TeacherReadiness;
  reason?: string;
  size?: ReadinessBadgeSize;
  showDetails?: boolean;
}

export function ReadinessBadge({ readiness, reason, size = 'md', showDetails = false }: ReadinessBadgeProps) {
  const meta = readinessSemantics[readiness as keyof typeof readinessSemantics];

  if (!meta) {
    const UnknownIcon = fallbackIcon;
    return <span className={`${styles.root} ${styles[size]}`} role="status" aria-label="Статус готовности не определён"><span aria-hidden="true"><StatusBadge intent="neutral" size={size} icon={<UnknownIcon size={readinessIconSizes[size]} fill="currentColor" />}>Статус не определён</StatusBadge></span></span>;
  }

  const Icon = readinessIcons[meta.icon];
  const details = showDetails ? (reason ?? (readiness === 'ready' ? 'Все обязательные сертификаты актуальны' : undefined)) : undefined;
  const accessibleLabel = details ? `${meta.label}. ${details}` : meta.label;

  return <span className={`${styles.root} ${styles[size]}`} role="status" aria-label={accessibleLabel}><span aria-hidden="true"><StatusBadge intent={meta.intent} size={size} icon={<Icon size={readinessIconSizes[size]} fill="currentColor" />}>{meta.label}</StatusBadge>{details && size !== 'sm' ? <span className={styles.reason}>{details}</span> : null}</span></span>;
}
