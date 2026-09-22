import { PageIntro } from '@/shared/ui/page-intro';
import styles from '../section-page.module.css';

export default function DashboardPage() {
  return (
    <div className={styles.page}>
      <PageIntro title="Dashboard" description="Обзор текущего состояния взаимодействия с учебными заведениями и ближайших задач команды." eyebrow="Рабочая область" />
      <div className={styles.cards}>
        <article className={styles.card}><span>Активные взаимодействия</span><strong>—</strong><small>Данные подключатся на следующем этапе</small></article>
        <article className={styles.card}><span>Этапы workflow</span><strong>14</strong><small>Шагов в базовом сценарии</small></article>
        <article className={styles.card}><span>Статус системы</span><strong className={styles.ready}>Frontend ready</strong><small>Mock-источники данных</small></article>
      </div>
    </div>
  );
}
