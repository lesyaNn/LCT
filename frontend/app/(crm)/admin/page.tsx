import Link from 'next/link';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { PageIntro } from '@/shared/ui/page-intro';
import styles from '../section-page.module.css';
export default function AdminPage() { return <div className={styles.page}><PageIntro title="Администрирование" description="Настройка системных справочников и маршрутов CRM." /><div className={styles.cards}><Link className={styles.card} href="/admin/workflow/templates"><span>Workflow</span><strong>Шаблоны</strong><small>Настройте этапы, их порядок и параметры <ArrowRight size={18} fill="currentColor" /></small></Link><Link className={styles.card} href="/admin/import"><span>Каталоги</span><strong>Импорт данных</strong><small>Загрузите XLSX, сопоставьте поля и проверьте изменения <ArrowRight size={18} fill="currentColor" /></small></Link></div></div>; }
