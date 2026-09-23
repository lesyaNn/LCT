import { loadDocumentation } from '@/shared/lib/docs-repository';
import { PageIntro } from '@/shared/ui/page-intro';
import { DocsPage } from '@/widgets/docs/docs-page';
import styles from '../section-page.module.css';

export default async function DocsRoute({ searchParams }: { searchParams: Promise<{ article?: string | string[] }> }) {
  const docs = await loadDocumentation();
  const requestedArticle = (await searchParams).article;
  const initialArticleId = Array.isArray(requestedArticle) ? requestedArticle[0] : requestedArticle;
  return <div className={styles.page}><PageIntro title="Документация" description="Инструкции по работе с CRM, workflow и правами доступа." /><DocsPage docs={docs} initialArticleId={initialArticleId} /></div>;
}
