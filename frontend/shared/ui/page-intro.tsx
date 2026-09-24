import styles from './page-intro.module.css';

interface PageIntroProps {
  title: string;
  description?: string;
}

export function PageIntro({ title, description }: PageIntroProps) {
  return (
    <section className={styles.intro}>
      <h1>{title}</h1>
      {description ? <p className={styles.description}>{description}</p> : null}
    </section>
  );
}
