import { loadDocumentation } from '@/shared/lib/docs-repository';
import { DocsPage } from '@/widgets/docs/docs-page';

export default async function DocsRoute({ searchParams }: { searchParams: Promise<{ article?: string | string[] }> }) {
  const docs = await loadDocumentation();
  const requestedArticle = (await searchParams).article;
  const initialArticleId = Array.isArray(requestedArticle) ? requestedArticle[0] : requestedArticle;
  return <DocsPage docs={docs} initialArticleId={initialArticleId} />;
}
