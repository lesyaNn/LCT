import styles from './avatar.module.css';

export function Avatar({ initials, size = 'm' }: { initials: string; size?: 's' | 'm' | 'l' }) {
  return <span className={`${styles.avatar} ${styles[size]}`} aria-hidden="true">{initials}</span>;
}
