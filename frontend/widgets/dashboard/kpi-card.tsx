import Link from 'next/link';
import type { ComponentType } from 'react';
import styles from './kpi-card.module.css';

export type KpiTone = 'brand' | 'neutral' | 'success' | 'warning' | 'danger';

interface KpiIconProps {
  fill?: string;
  size?: number;
}

interface KpiCardProps {
  title: string;
  value: string;
  caption: string;
  icon: ComponentType<KpiIconProps>;
  tone: KpiTone;
  href?: string;
  ariaLabel?: string;
}

function KpiCardContent({ title, value, caption, icon: Icon, tone }: Omit<KpiCardProps, 'href' | 'ariaLabel'>) {
  return (
    <>
      <div className={styles.header}>
        <span className={`${styles.icon} ${styles[tone]}`} aria-hidden="true">
          <Icon size={24} fill="currentColor" />
        </span>
        <span className={styles.title}>{title}</span>
      </div>
      <strong className={styles.value}>{value}</strong>
      <span className={styles.caption}>{caption}</span>
    </>
  );
}

export function KpiCard({ title, value, caption, icon, tone, href, ariaLabel }: KpiCardProps) {
  const content = <KpiCardContent title={title} value={value} caption={caption} icon={icon} tone={tone} />;

  if (href) {
    return (
      <Link className={`${styles.card} ${styles[tone]} ${styles.interactive}`} href={href} aria-label={ariaLabel}>
        {content}
      </Link>
    );
  }

  return <article className={`${styles.card} ${styles[tone]}`}>{content}</article>;
}
