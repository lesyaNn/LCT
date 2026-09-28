import { PageIntro } from '@/shared/ui/page-intro';
import { AuditPage } from '@/widgets/audit/audit-page';

export default function AuditRoute() {
  return <><PageIntro title="История изменений" description="Здесь отображаются действия пользователей и изменения данных в системе." /><AuditPage /></>;
}
