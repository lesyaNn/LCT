import Link from 'next/link';
import type { ComponentType } from 'react';
import styles from './kpi-card.module.css';

export type KpiTone = 'brand' | 'orange' | 'warning' | 'danger';

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

function KpiCardContent({ title, value, caption, icon: Icon }: Omit<KpiCardProps, 'href' | 'ariaLabel'>) {
  return (
    <>
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden="true">
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
  const className = `${styles.card} ${styles[tone]} ${tone === 'orange' ? 'Theme_root_rtk_default_light' : ''}`;

  if (href) {
    return (
      <Link className={`${className} ${styles.interactive}`} href={href} aria-label={ariaLabel}>
        {content}
      </Link>
    );
  }

  return <article className={className}>{content}</article>;
}
