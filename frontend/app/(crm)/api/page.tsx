import { PageIntro } from '@/shared/ui/page-intro';
import { ApiDocumentationPage } from '@/widgets/api-documentation/api-documentation-page';

export default function ApiRoute() {
  return <><PageIntro title="API" description="Методы CRM, параметры запросов и ограничения" /><ApiDocumentationPage /></>;
}
