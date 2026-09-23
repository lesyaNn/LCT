import { PageIntro } from '@/shared/ui/page-intro';
import { ReportsPage } from '@/widgets/reports/reports-page';

export default function ReportsRoute() {
  return <><PageIntro title="Отчёты" description="Соберите параметры отчёта и отслеживайте задачи формирования в одной рабочей области." /><ReportsPage /></>;
}
