import styles from './page-intro.module.css';

interface PageIntroProps {
  title: string;
  description: string;
  eyebrow?: string;
}

export function PageIntro({ title, description, eyebrow = 'Раздел CRM' }: PageIntroProps) {
  return (
    <section className={styles.intro}>
      <p className={styles.eyebrow}>{eyebrow}</p>
      <h1>{title}</h1>
      <p className={styles.description}>{description}</p>
    </section>
  );
}
