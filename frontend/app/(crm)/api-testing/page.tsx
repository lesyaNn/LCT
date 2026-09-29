import { PageIntro } from '@/shared/ui/page-intro';
import { ApiTestingPage } from '@/widgets/api-testing/api-testing-page';

export default function ApiTestingRoute() {
  return <><PageIntro title="Тестирование API" description="Проверка интеграции CRM с внешними системами и внутренних API-методов" /><ApiTestingPage /></>;
}
