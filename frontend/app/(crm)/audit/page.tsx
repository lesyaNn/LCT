import { PageIntro } from '@/shared/ui/page-intro';
import { AuditPage } from '@/widgets/audit/audit-page';

export default function AuditRoute() {
  return <><PageIntro title="Аудит действий" description="Полный журнал действий пользователей и изменений в системе." /><AuditPage /></>;
}
