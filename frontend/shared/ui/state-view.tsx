import { useId, type ReactNode } from 'react';
import styles from './state-view.module.css';

export type StatePresentation = 'compact' | 'large';

interface StateViewProps {
  title: string;
  description?: string;
  eyebrow?: string;
  eyebrowStyle?: 'label' | 'code';
  visual?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  presentation?: StatePresentation;
  headingLevel?: 1 | 2 | 3;
  role?: 'status' | 'alert';
  ariaLive?: 'polite' | 'assertive' | 'off';
  className?: string;
}

export function StateView({
  title,
  description,
  eyebrow,
  eyebrowStyle = 'label',
  visual,
  icon,
  actions,
  presentation = 'compact',
  headingLevel = 2,
  role,
  ariaLive,
  className = '',
}: StateViewProps) {
  const titleId = useId();
  const Heading = `h${headingLevel}` as 'h1' | 'h2' | 'h3';
  return (
    <section
      aria-labelledby={titleId}
      aria-live={ariaLive === 'off' ? undefined : ariaLive}
      className={`${styles.state} ${styles[presentation]} ${className}`}
      role={role}
    >
      <div className={styles.content}>
        {icon ? <span className={styles.icon} aria-hidden="true">{icon}</span> : null}
        {eyebrow ? <p className={eyebrowStyle === 'code' ? styles.code : styles.label}>{eyebrow}</p> : null}
        <Heading className={styles.title} id={titleId}>{title}</Heading>
        {description ? <p className={styles.description}>{description}</p> : null}
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>
      {visual ? <div className={styles.visual}>{visual}</div> : null}
    </section>
  );
}
