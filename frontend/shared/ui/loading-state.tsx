import styles from './loading-state.module.css';

export function LoadingState({ title = 'Загрузка', description, compact = false }: { title?: string; description?: string; compact?: boolean }) {
  return (
    <section className={`${styles.state} ${compact ? styles.compact : ''}`} aria-busy="true" aria-live="polite" role="status">
      <span className={styles.spinner} aria-hidden="true" />
      <div><h1>{title}</h1>{description ? <p>{description}</p> : null}</div>
    </section>
  );
}
