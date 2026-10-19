'use client';

import Search from '@atomaro/icons/24/action/Search';
import Edit from '@atomaro/icons/24/editor/Edit';
import Link from 'next/link';
import Image from 'next/image';
import { useMemo, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { EmptyState } from '@/shared/ui/empty-state';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Input } from '@/shared/ui/rtk/form-controls';
import type { DocsArticle, DocsSection, DocsSnapshot } from '@/shared/lib/docs-repository';
import styles from './docs-page.module.css';

interface DocsPageProps {
  docs: DocsSnapshot;
  initialArticleId?: string;
}

function plainTextFromMarkdown(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/[*_`>|~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function articleSearchText(article: DocsArticle): string {
  return `${article.title} ${article.sectionTitle} ${plainTextFromMarkdown(article.content)}`.toLocaleLowerCase('ru-RU');
}

function searchFragment(article: DocsArticle, query: string): string {
  const plain = plainTextFromMarkdown(article.content);
  const position = plain.toLocaleLowerCase('ru-RU').indexOf(query);
  const start = Math.max(0, position - 45);
  return `${start ? '…' : ''}${plain.slice(start, start + 105)}${start + 105 < plain.length ? '…' : ''}`;
}

function DocsNavigation({ sections, activeArticleId, query, onQueryChange, onNavigate }: { sections: DocsSection[]; activeArticleId?: string; query: string; onQueryChange: (value: string) => void; onNavigate?: () => void }) {
  const articles = sections.flatMap((section) => section.articles);
  const normalizedQuery = query.trim().toLocaleLowerCase('ru-RU');
  const results = normalizedQuery ? articles.filter((article) => articleSearchText(article).includes(normalizedQuery))
    .sort((left, right) => Number(right.title.toLocaleLowerCase('ru-RU').includes(normalizedQuery)) - Number(left.title.toLocaleLowerCase('ru-RU').includes(normalizedQuery)))
    .slice(0, 12) : [];
  return <>
    <label className={styles.searchField}><Search size={18} fill="currentColor" aria-hidden="true" /><span className={styles.visuallyHidden}>Поиск по документации</span><Input type="search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Поиск по документации" aria-label="Поиск по документации" /></label>
    {normalizedQuery ? <div className={styles.searchResults} aria-label="Результаты поиска">{results.length ? results.map((article) => <Link className={styles.searchResult} href={article.href} key={article.id} onClick={onNavigate}><strong>{article.title}</strong><span>{searchFragment(article, normalizedQuery)}</span></Link>) : <EmptyState icon={<Search size={18} fill="currentColor" />} title="Ничего не найдено" description="Попробуйте изменить поисковый запрос." headingLevel={3} />}</div> : null}
    <nav className={styles.docsNav} aria-label="Навигация по документации">
      <Link className={`${styles.homeLink} ${!activeArticleId ? styles.activeArticle : ''}`} href="/docs" onClick={onNavigate}>Справочный центр</Link>
      {sections.filter((section) => section.articles.length).map((section) => {
        const active = section.articles.some((article) => article.id === activeArticleId);
        return <details className={styles.navSection} key={`${section.id}-${activeArticleId ?? 'home'}`} open={active || (!activeArticleId && section.id === 'user-guide')}>
          <summary>{section.title}</summary>
          <ul>{section.articles.map((article) => <li key={article.id}><Link className={activeArticleId === article.id ? styles.activeArticle : undefined} href={article.href} onClick={onNavigate} aria-current={activeArticleId === article.id ? 'page' : undefined}>{article.title}</Link></li>)}</ul>
        </details>;
      })}
    </nav>
  </>;
}

const imageDimensions: Record<string, [number, number]> = {
  'docs-audit.jpg': [1090, 390],
  'docs-catalogs.jpg': [1150, 850],
  'docs-dashboard-matrix.jpg': [1090, 620],
  'docs-dashboard.jpg': [1235, 810],
  'docs-health-score.jpg': [1150, 900],
  'docs-import.jpg': [1090, 430],
  'docs-notifications.jpg': [1150, 350],
  'docs-passport-documents.jpg': [1150, 510],
  'docs-passport-licenses.jpg': [1090, 530],
  'docs-passport-overview.jpg': [1150, 830],
  'docs-passport-products.jpg': [1100, 445],
  'docs-reports-form.jpg': [1150, 900],
  'docs-reports-preview.jpg': [1130, 905],
  'docs-reports-statistics.jpg': [1130, 905],
  'docs-universities-cards.jpg': [1150, 690],
  'docs-universities-map.jpg': [1090, 760],
  'docs-universities-table.jpg': [1150, 800],
  'docs-workflow-default-tasks.jpg': [1150, 850],
  'docs-workflow-detail-top.jpg': [1150, 850],
  'docs-workflow-kanban.jpg': [1150, 850],
  'docs-workflow-list.jpg': [1150, 840],
  'docs-workflow-template-editor.jpg': [1150, 850],
};

const markdownComponents: Components = {
  code: ({ children, ...props }) => String(children).trim() === ':edit:'
    ? <span className={styles.inlineIcon} role="img" aria-label="Редактировать"><Edit size={18} fill="currentColor" /></span>
    : <code {...props}>{children}</code>,
  a: ({ href, children, ...props }) => {
    if (href?.startsWith('/')) return <Link href={href} {...props}>{children}</Link>;
    return <a href={href} target={href?.startsWith('#') ? undefined : '_blank'} rel={href?.startsWith('#') ? undefined : 'noopener noreferrer'} {...props}>{children}</a>;
  },
  table: ({ children, ...props }) => <div className={styles.tableWrap}><table {...props}>{children}</table></div>,
  pre: ({ children, ...props }) => <pre className={styles.codeBlock} {...props}>{children}</pre>,
  img: ({ src, alt }) => {
    if (!src || typeof src !== 'string' || !src.startsWith('/docs/images/')) return null;
    const [width, height] = imageDimensions[src.split('/').at(-1) ?? ''] ?? [1200, 760];
    return <span className={styles.figure} role="figure" aria-label={alt ?? ''}><Image src={src} alt={alt ?? ''} width={width} height={height} sizes="(max-width: 768px) 100vw, (max-width: 1200px) 80vw, 900px" loading="lazy" /><span className={styles.caption}>{alt}</span></span>;
  },
};

function ArticleContent({ article }: { article: DocsArticle }) {
  const faq = article.id === 'help/faq' ? article.content.split(/^### /m).slice(1).map((entry) => { const [question, ...answer] = entry.split('\n'); return { question: question.trim(), answer: answer.join('\n').trim() }; }) : [];
  return <article className={styles.article} aria-labelledby="docs-article-title"><header className={styles.articleHeader}><p className={styles.articleSection}>{article.sectionTitle}</p><h1 id="docs-article-title">{article.title}</h1></header><div className={styles.markdown}>{article.id === 'help/faq' ? <div className={styles.faqList}>{faq.map(({ question, answer }) => <details className={styles.faqItem} key={question}><summary>{question}</summary><div><ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown></div></details>)}</div> : <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>{article.content}</ReactMarkdown>}</div></article>;
}

function DocsLanding({ docs }: { docs: DocsSnapshot }) {
  const cards = [
    ['user-guide/getting-started', 'Начало работы', 'Основные возможности CRM и первые действия.'],
    ['user-guide/universities', 'Работа с вузами', 'Паспорт, программы, продукты и ответственные.'],
    ['user-guide/workflow', 'Workflow', 'Этапы, комментарии, файлы и задачи.'],
    ['user-guide/notifications', 'Уведомления', 'События, которые требуют внимания.'],
    ['user-guide/reports', 'Отчёты', 'Фильтрация, формирование и выгрузка.'],
  ];
  return <div className={styles.landing}><p className={styles.eyebrow}>Помощь по CRM</p><h1>Справочный центр CRM</h1><p>Здесь собраны инструкции по работе с системой: поиск вуза, паспорт, Workflow, уведомления и отчёты. Разделы для руководителя и администратора находятся в навигации.</p><div className={styles.landingCards}>{cards.map(([id, title, description]) => { const article = docs.articles.find((item) => item.id === id); return article ? <Link href={article.href} key={id}><strong>{title}</strong><span>{description}</span></Link> : null; })}</div></div>;
}

export function DocsPage({ docs, initialArticleId }: DocsPageProps) {
  const [query, setQuery] = useState('');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const article = initialArticleId ? docs.articles.find((item) => item.id === initialArticleId) : undefined;
  const invalidArticle = Boolean(initialArticleId && !article);
  const selectedArticleId = article?.id;
  const mobileNavigation = useMemo(() => <DocsNavigation sections={docs.sections} activeArticleId={selectedArticleId} query={query} onQueryChange={setQuery} onNavigate={() => setMobileNavOpen(false)} />, [docs.sections, query, selectedArticleId]);

  return <section className={styles.docsShell}>
    <div className={styles.mobileToolbar}><strong>Навигация по документации</strong><IconButton icon="menu" label="Открыть навигацию по документации" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen(true)} /></div>
    <aside className={styles.sidebar}><DocsNavigation sections={docs.sections} activeArticleId={selectedArticleId} query={query} onQueryChange={setQuery} /></aside>
    {mobileNavOpen ? <Drawer title="Документация" onClose={() => setMobileNavOpen(false)}>{mobileNavigation}</Drawer> : null}
    <main className={styles.content}>{article ? <ArticleContent article={article} /> : invalidArticle ? <EmptyState presentation="large" title="Статья не найдена" description="Проверьте ссылку или выберите материал в навигации." /> : <DocsLanding docs={docs} />}</main>
  </section>;
}
