import Image from 'next/image';
import Link from 'next/link';
import styles from './welcome.module.css';

export default function HomePage() {
  return <main className={styles.page}>
    <div className={styles.brand}><Image src="/brand/rostelecom-horizontal.svg" alt="Ростелеком" width={238} height={62} priority unoptimized /></div>
    <section className={styles.card} aria-labelledby="welcome-title">
      <span className={styles.accent} aria-hidden="true" />
      <p className={styles.eyebrow}>CRM ИТ-Школа</p>
      <h1 id="welcome-title">Добро пожаловать</h1>
      <p>Единое пространство для работы с вузами, программами и этапами сотрудничества.</p>
      <Link className={styles.login} href="/login">Войти через Ростелеком</Link>
    </section>
  </main>;
}
