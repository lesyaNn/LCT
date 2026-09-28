import { PageIntro } from '@/shared/ui/page-intro';
import { AuditPage } from '@/widgets/audit/audit-page';
import styles from '@/widgets/audit/audit-page.module.css';

export default function AuditRoute() {
  return <div className={styles.route}><PageIntro title="История изменений" description="Здесь отображаются действия пользователей и изменения данных в системе." /><AuditPage /></div>;
}
