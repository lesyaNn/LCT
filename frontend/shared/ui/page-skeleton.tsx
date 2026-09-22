import styles from './route-state.module.css';

export function PageSkeleton({ cardCount = 3, variant = 'default' }: { cardCount?: number; variant?: 'default' | 'dashboard' }) {
  return (
    <section className={styles.loading} aria-live="polite" aria-busy="true">
      <div className={styles.loadingHeader} role="status">
        <span className={styles.loader} aria-hidden="true" />
        <p className={styles.loadingText}>Загружаем раздел…</p>
      </div>
      <div className={styles.skeleton} aria-hidden="true">
        <span className={`${styles.skeletonLine} ${styles.skeletonLineShort}`} />
        <span className={styles.skeletonLine} />
        <div className={`${styles.skeletonCards} ${variant === 'dashboard' ? styles.skeletonCardsDashboard : ''}`}>
          {Array.from({ length: cardCount }, (_, index) => <span className={styles.skeletonCard} key={index} />)}
        </div>
      </div>
    </section>
  );
}
