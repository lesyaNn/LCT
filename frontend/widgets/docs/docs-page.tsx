'use client';

import Search from '@atomaro/icons/24/action/Search';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Input } from '@/shared/ui/rtk/form-controls';
import type { DocsArticle, DocsSection, DocsSnapshot } from '@/shared/lib/docs-repository';
import styles from './docs-page.module.css';

interface DocsPageProps {
  docs: DocsSnapshot;
  initialArticleId?: string;
}

function articleSearchText(article: DocsArticle): string {
  return `${article.title} ${article.sectionTitle} ${article.headings.join(' ')} ${article.content}`.toLocaleLowerCase('ru-RU');
}

function DocsNavigation({ sections, activeArticleId, query, onQueryChange, onNavigate }: { sections: DocsSection[]; activeArticleId?: string; query: string; onQueryChange: (value: string) => void; onNavigate?: () => void }) {
  const articles = sections.flatMap((section) => section.articles);
  const normalizedQuery = query.trim().toLocaleLowerCase('ru-RU');
  const results = normalizedQuery ? articles.filter((article) => articleSearchText(article).includes(normalizedQuery)).slice(0, 12) : [];
  return <>
    <label className={styles.searchField}><Search size={18} fill="currentColor" aria-hidden="true" /><span className={styles.visuallyHidden}>Поиск по документации</span><Input type="search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Поиск по документации" aria-label="Поиск по документации" /></label>
    {normalizedQuery ? <div className={styles.searchResults} aria-label="Результаты поиска">{results.length ? results.map((article) => <Link className={styles.searchResult} href={article.href} key={article.id} onClick={onNavigate}><strong>{article.title}</strong><span>{article.sectionTitle}</span></Link>) : <p className={styles.searchEmpty}>Ничего не найдено</p>}</div> : null}
    <nav className={styles.docsNav} aria-label="Навигация по документации">
      {sections.map((section) => <section className={styles.navSection} key={section.id}><h2>{section.title}</h2>{section.articles.length ? <ul>{section.articles.map((article) => <li key={article.id}><Link className={activeArticleId === article.id ? styles.activeArticle : undefined} href={article.href} onClick={onNavigate} aria-current={activeArticleId === article.id ? 'page' : undefined}>{article.title}</Link></li>)}</ul> : <p className={styles.navEmpty}>Материал пока недоступен</p>}</section>)}
    </nav>
  </>;
}

const markdownComponents: Components = {
  a: ({ href, children, ...props }) => {
    if (href?.startsWith('/docs')) return <Link href={href} {...props}>{children}</Link>;
    return <a href={href} target={href?.startsWith('#') ? undefined : '_blank'} rel={href?.startsWith('#') ? undefined : 'noopener noreferrer'} {...props}>{children}</a>;
  },
  table: ({ children, ...props }) => <div className={styles.tableWrap}><table {...props}>{children}</table></div>,
  pre: ({ children, ...props }) => <pre className={styles.codeBlock} {...props}>{children}</pre>,
};

function ArticleContent({ article }: { article: DocsArticle }) {
  return <article className={styles.article} aria-labelledby="docs-article-title"><header className={styles.articleHeader}><p className={styles.articleSection}>{article.sectionTitle}</p><h1 id="docs-article-title">{article.title}</h1></header><div className={styles.markdown}><ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>{article.content}</ReactMarkdown></div></article>;
}

function EmptyDocumentation({ sections, invalidArticle }: { sections: DocsSection[]; invalidArticle: boolean }) {
  return <section className={styles.emptyState} aria-labelledby="docs-empty-title"><p className={styles.eyebrow}>{invalidArticle ? 'Документация' : 'Раздел CRM'}</p><h1 id="docs-empty-title">{invalidArticle ? 'Материал пока недоступен' : 'Документация готовится'}</h1><p>{invalidArticle ? 'Запрошенная статья отсутствует или ещё не опубликована.' : 'Статьи появятся здесь после публикации контента P5-15-01. Навигация уже готова для подключения Markdown-файлов.'}</p><div className={styles.sectionOverview}>{sections.map((section) => <div className={styles.sectionSummary} key={section.id}><h2>{section.title}</h2>{section.topics.length ? <ul>{section.topics.map((topic) => <li key={topic.slug}>{topic.title}</li>)}</ul> : <p>Раздел ожидает материалы.</p>}</div>)}</div></section>;
}

export function DocsPage({ docs, initialArticleId }: DocsPageProps) {
  const [query, setQuery] = useState('');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const article = initialArticleId ? docs.articles.find((item) => item.id === initialArticleId) : docs.articles[0];
  const invalidArticle = Boolean(initialArticleId && !article);
  const selectedArticleId = article?.id;
  const mobileNavigation = useMemo(() => <DocsNavigation sections={docs.sections} activeArticleId={selectedArticleId} query={query} onQueryChange={setQuery} onNavigate={() => setMobileNavOpen(false)} />, [docs.sections, query, selectedArticleId]);

  return <section className={styles.docsShell}>
    <div className={styles.mobileToolbar}><strong>Навигация по документации</strong><IconButton icon="menu" label="Открыть навигацию по документации" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen(true)} /></div>
    <aside className={styles.sidebar}><DocsNavigation sections={docs.sections} activeArticleId={selectedArticleId} query={query} onQueryChange={setQuery} /></aside>
    {mobileNavOpen ? <Drawer title="Документация" onClose={() => setMobileNavOpen(false)}>{mobileNavigation}</Drawer> : null}
    <main className={styles.content}>{article ? <ArticleContent article={article} /> : <EmptyDocumentation sections={docs.sections} invalidArticle={invalidArticle} />}</main>
  </section>;
}
