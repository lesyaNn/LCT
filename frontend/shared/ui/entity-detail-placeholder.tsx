import { PageIntro } from '@/shared/ui/page-intro';
import styles from './entity-detail-placeholder.module.css';

interface EntityDetailPlaceholderProps {
  eyebrow: string;
  title: string;
  description: string;
  routeId: string;
}

export function EntityDetailPlaceholder({ eyebrow, title, description, routeId }: EntityDetailPlaceholderProps) {
  return (
    <div className={styles.page}>
      <PageIntro eyebrow={eyebrow} title={title} description={description} />
      <section className={styles.placeholder} aria-labelledby="detail-placeholder-title">
        <h2 id="detail-placeholder-title">Детальный экран подготовлен</h2>
        <p>Данные сущности подключатся в соответствующей функциональной задаче.</p>
        <p className={styles.routeId}><span>Идентификатор маршрута</span><code>{routeId}</code></p>
      </section>
    </div>
  );
}
