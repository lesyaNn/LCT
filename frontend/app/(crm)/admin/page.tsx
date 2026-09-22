import { PageIntro } from '@/shared/ui/page-intro';
import styles from '../section-page.module.css';
export default function AdminPage() { return <div className={styles.page}><PageIntro title="Администрирование" description="Frontend-оболочка административного раздела доступна mock-пользователю с ролью администратора." /></div>; }
