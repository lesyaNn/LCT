import Link from 'next/link';
import { PageIntro } from '@/shared/ui/page-intro';
import styles from '../section-page.module.css';
const sections = [
  ['Пользователи и права', '/admin/users'],
  ['Управление каталогами', '/admin/catalogs'],
  ['Импорт каталогов', '/admin/import'],
  ['Шаблоны Workflow', '/admin/workflow/templates'],
] as const;

export default function AdminPage() {
  return <div className={styles.page}>
    <PageIntro title="Администрирование" description="Выберите раздел в боковом меню." />
    <section className={styles.adminOverview} aria-label="Разделы администрирования">
      {sections.map(([label, href]) => <Link className={styles.adminLink} href={href} key={href}><span>{label}</span><span aria-hidden="true">→</span></Link>)}
    </section>
  </div>;
}
