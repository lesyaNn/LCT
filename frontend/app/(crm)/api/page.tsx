import { loadDocumentation } from '@/shared/lib/docs-repository';
import { PageIntro } from '@/shared/ui/page-intro';
import { ApiDocumentationPage } from '@/widgets/api-documentation/api-documentation-page';

export default async function ApiRoute() {
  const docs = await loadDocumentation();
  const guide = docs.articles.find(article => article.id === 'api/integration')?.content
    ?? 'Инструкция временно недоступна. Перечень методов можно открыть на вкладке Все методы.';
  return <><PageIntro title="API" description="Подключение внешних сервисов, методы CRM и примеры запросов" /><ApiDocumentationPage guide={guide} /></>;
}
